const {onSchedule} = require("firebase-functions/v2/scheduler");
const admin = require("firebase-admin");
const functions = require("firebase-functions");
const axios = require("axios");
const FormData = require("form-data");

// ✅ Get bot token from environment variable (Cloud Functions v2)
function getTelegramToken() {
    return process.env.TELEGRAM_BOT_TOKEN || null;
}

// Initialize admin only once
let db;
try {
  if (!admin.apps.length) {
    admin.initializeApp({
      // ✅ point Admin SDK to your RTDB region
      databaseURL: "https://leaderboard-98e8c-default-rtdb.asia-southeast1.firebasedatabase.app",
    });
  }
  db = admin.database();
} catch (error) {
  console.error("Initialization error:", error);
}

// ============================================================================
// USER CATEGORY IDENTIFICATION
// ============================================================================
/**
 * Identifies user category - CRITICAL for proper processing
 * Categories:
 * 1. "real" - Real users from the app (userType === "real")
 * 2. "fake_inactive" - Fake users that never update (isFakeInactive === true)
 * 3. "fake_active" - Fake users that update normally (default)
 */
function getUserCategory(user) {
  // PRIORITY 1: Real users (from mobile app) - NEVER modify their study data
  if (user.userType === "real") {
    return "real";
  }
  
  // PRIORITY 2: Fake inactive users (for show only) - NEVER update
  if (user.isFakeInactive === true) {
    return "fake_inactive";
  }
  
  // PRIORITY 3: Fake active users - Update normally
  // This includes users with userType="fake" or no userType field
  return "fake_active";
}

// ============================================================================
// HELPER FUNCTIONS (UNCHANGED)
// ============================================================================

// Clamp helper
function clamp(num, min, max) {
  return Math.min(Math.max(num, min), max);
}

// Get target online percentage based on hour
function getTargetOnlinePercentage(hour) {
  if (hour >= 23 || hour < 5) return { min: 0.02, max: 0.04 }; // 11 PM - 5 AM: 2-4%
  if (hour >= 5 && hour < 8) return { min: 0.15, max: 0.35 };  // 5 AM - 8 AM: 15-35%
  if (hour >= 17 && hour < 22) return { min: 0.30, max: 0.60 }; // 5 PM - 10 PM: 30-60%
  return { min: 0.10, max: 0.40 }; // Rest of time: 10-40%
}

function isWithinReportWindow(istTime) {
  const hour = istTime.getUTCHours();
  const minute = istTime.getUTCMinutes();

  return (
    (hour === 23 && minute >= 55) || // 11:55 PM - 11:59 PM IST
    (hour === 0 && minute <= 5)      // 12:00 AM - 12:05 AM IST
  );
}

// Initialize user performance profile (ONLY for fake active users)
function initializeUserProfile(uid) {
  const rnd = Math.random() * 100;
  
  // Distribution: 2-5% top, 20% high, 40% medium, rest low
  if (rnd < 3.5) { // ~3.5% top performers (11-14 hours)
    return {
      perfType: "top",
      dailyTarget: +(11 + Math.random() * 3).toFixed(1),
      studyPace: 0.9 + Math.random() * 0.1, // 90-100% efficiency
      onlinePreference: 0.8 + Math.random() * 0.2 // Prefer to be online
    };
  } else if (rnd < 23.5) { // ~20% high performers (8-10 hours)
    return {
      perfType: "high",
      dailyTarget: +(8 + Math.random() * 2).toFixed(1),
      studyPace: 0.8 + Math.random() * 0.15, // 80-95% efficiency
      onlinePreference: 0.6 + Math.random() * 0.3
    };
  } else if (rnd < 63.5) { // ~40% medium performers (5-8 hours)
    return {
      perfType: "medium", 
      dailyTarget: +(5 + Math.random() * 3).toFixed(1),
      studyPace: 0.7 + Math.random() * 0.2, // 70-90% efficiency
      onlinePreference: 0.4 + Math.random() * 0.4
    };
  } else { // ~36.5% low performers (0-4 hours)
    return {
      perfType: "low",
      dailyTarget: +(Math.random() * 4).toFixed(1),
      studyPace: 0.5 + Math.random() * 0.3, // 50-80% efficiency
      onlinePreference: 0.2 + Math.random() * 0.4
    };
  }
}

// Manage online/offline state transitions (ONLY for fake active users)
async function manageOnlineStates(users, hour, updates) {
  const targetRange = getTargetOnlinePercentage(hour);
  const targetPercentage = targetRange.min + Math.random() * (targetRange.max - targetRange.min);
  
  // Filter only fake active users - EXCLUDE real and inactive
  const fakeActiveUsers = Object.entries(users).filter(([uid, user]) => {
    const category = getUserCategory(user);
    return category === "fake_active";  // ONLY fake active users
  });
  
  const totalFakeActiveUsers = fakeActiveUsers.length;
  if (totalFakeActiveUsers === 0) return;
  
  const currentOnlineUsers = fakeActiveUsers.filter(([uid, user]) => user.online).length;
  const currentOnlinePercentage = currentOnlineUsers / totalFakeActiveUsers;
  
  const targetOnlineCount = Math.floor(totalFakeActiveUsers * targetPercentage);
  const currentOnlineCount = currentOnlineUsers;
  
  console.log(`Hour ${hour}: Target ${(targetPercentage*100).toFixed(1)}% (${targetOnlineCount}/${totalFakeActiveUsers}), Current ${(currentOnlinePercentage*100).toFixed(1)}% (${currentOnlineCount}/${totalFakeActiveUsers})`);
  
  // Gradual transition - change max 10% of users per update
  const maxChanges = Math.max(1, Math.floor(totalFakeActiveUsers * 0.1));
  let changes = 0;
  
  if (currentOnlineCount < targetOnlineCount) {
    // Need to bring users online
    const offlineUsers = fakeActiveUsers.filter(([uid, user]) => !user.online);
    const shuffled = offlineUsers.sort(() => Math.random() - 0.5);
    
    for (const [uid, user] of shuffled) {
      if (changes >= maxChanges) break;
      if (currentOnlineCount + changes >= targetOnlineCount) break;
      
      // Check if user hasn't reached daily target
      const todayHours = user.todayHours || 0;
      const dailyTarget = user.dailyTarget || 5;
      
      // More likely to come online if below target and during their preferred hours
      const shouldComeOnline = todayHours < dailyTarget && 
        Math.random() < (user.onlinePreference || 0.5);
      
      if (shouldComeOnline) {
        updates[`leaderboard/${uid}/online`] = true;
        updates[`leaderboard/${uid}/status`] = "Online";
        updates[`leaderboard/${uid}/lastOnlineTime`] = new Date().toISOString();
        changes++;
      }
    }
  } else if (currentOnlineCount > targetOnlineCount) {
    // Need to take users offline
    const onlineUsers = fakeActiveUsers.filter(([uid, user]) => user.online);
    
    // Sort by how long they've been online (take longest online users offline first)
    const sorted = onlineUsers.sort((a, b) => {
      const aTime = a[1].lastOnlineTime ? new Date(a[1].lastOnlineTime) : new Date(0);
      const bTime = b[1].lastOnlineTime ? new Date(b[1].lastOnlineTime) : new Date(0);
      return aTime - bTime; // Older online time first
    });
    
    for (const [uid, user] of sorted) {
      if (changes >= maxChanges) break;
      if (currentOnlineCount - changes <= targetOnlineCount) break;
      
      // Check minimum online duration (at least 5 minutes)
      const lastOnlineTime = user.lastOnlineTime ? new Date(user.lastOnlineTime) : new Date();
      const onlineDuration = (new Date() - lastOnlineTime) / 1000 / 60; // in minutes
      
      if (onlineDuration >= 5) {
        updates[`leaderboard/${uid}/online`] = false;
        updates[`leaderboard/${uid}/status`] = "Offline";
        changes++;
      }
    }
  }
}

// Weekly reset trigger (Sunday 23:55-23:59 IST OR Monday 00:00-00:05 IST)
async function shouldResetWeek(now) {
    try {
        console.log("LOG A → shouldResetWeek() called");
        
        // ✅ 1. Test Reset Flag: Trigger reset ONCE after deploy
        const testFlagSnap = await db.ref("_global/testForceReset").once("value");
        const testFlag = testFlagSnap.val();

        if (testFlag === true) {
            console.log("LOG B → testForceReset detected, forcing reset");
            
            // Disable it immediately so reset happens only once
            await db.ref("_global/testForceReset").set(false);

            return true;  // ✅ Force reset this cycle ONLY
        }

        // ✅ 2. Normal weekly reset logic
        const istOffset = 5.5 * 60 * 60 * 1000;
        const istTime = new Date(now.getTime() + istOffset);

        const day = istTime.getUTCDay(); 
        const hour = istTime.getUTCHours();
        const minute = istTime.getUTCMinutes();

        // Check last reset date
        const lastResetSnapshot = await db.ref("_global/lastWeeklyReset").once("value");
        const lastReset = lastResetSnapshot.val();

        if (lastReset) {
            const lastResetDate = new Date(lastReset);
            const daysSinceReset = (now - lastResetDate) / (1000 * 60 * 60 * 24);

            if (daysSinceReset < 6) {
                return false;
            }
        }

        // ✅ PRODUCTION: Reset window (Sunday 11:59 PM IST)
        const isResetWindow =
          (day === 0 && hour === 23 && minute >= 55) ||
          (day === 1 && hour === 0 && minute <= 5);

        if (isResetWindow) {
            console.log(`✅ Weekly Reset Window IST: ${istTime.toISOString()}`);
        }

        return isResetWindow;

    } catch (error) {
        console.error("Error in shouldResetWeek:", error);
        return false;
    }
}

// Save top 3 to _global before weekly reset
async function saveTop3BeforeReset(users) {
  try {
    console.log("📊 Calculating top 3 rankers before reset...");
    
    // Get all users with weekHours, excluding inactive users
    const rankedUsers = Object.entries(users)
      .filter(([uid, user]) => {
        const category = getUserCategory(user);
        // Include real and fake_active users with activity
        return (user.weekHours || 0) > 0 && category !== "fake_inactive";
      })
      .map(([uid, user]) => ({
        name: user.name || "Unknown",
        weekHours: user.weekHours || 0,
        score: user.score || 0,
        avatar_id: user.avatarId || "1",
        uid: uid,
        userType: user.userType || "fake"
      }))
      .sort((a, b) => b.weekHours - a.weekHours) // Sort by weekHours descending
      .slice(0, 3); // Take top 3
    
    if (rankedUsers.length > 0) {
      // Save to _global/lastWeekTop3
      await db.ref("_global/lastWeekTop3").set(rankedUsers);
      await db.ref("_global/lastWeekTop3SavedAt").set(new Date().toISOString());
      
      console.log(`✅ Saved top 3 rankers:`);
      rankedUsers.forEach((u, i) => {
        console.log(`   ${i+1}. ${u.name} - ${u.weekHours}h (${u.userType})`);
      });
    } else {
      console.log("⚠️ No users with activity to save as top 3");
    }
    
    return rankedUsers;
  } catch (error) {
    console.error("❌ Error saving top 3:", error);
    return [];
  }
}



// ============================================================================
// COMBINED SCHEDULER - Runs both tasks at same time
// ============================================================================

/**
 * ✅ COMBINED FUNCTION - Runs leaderboard + notifications together
 * This reduces invocations from 17,280 to 8,640 per month
 */
exports.scheduledTasks = onSchedule(
  {
    schedule: "every 5 minutes",
    timeZone: "Asia/Kolkata",
    secrets: ["TELEGRAM_BOT_TOKEN"],
  },
  async (event) => {
    console.log('\n🔄 ==================== COMBINED SCHEDULER ====================');
    console.log(`⏰ Time: ${new Date().toISOString()}`);
    
    try {
      // ✅ Run both tasks in parallel (saves time!)
      const [leaderboardResult, notificationResult] = await Promise.all([
        runLeaderboardUpdate(),
        runNotificationCheck()
      ]);
      
      console.log('✅ ==================== BOTH TASKS COMPLETE ====================\n');
      return null;
    } catch (error) {
      console.error('❌ Combined scheduler error:', error);
      return null;
    }
  }
);

// ============================================================================
// EXTRACTED LOGIC FUNCTIONS
// ============================================================================

async function runLeaderboardUpdate() {
  try {
    const now = new Date();
    console.log("\n📊 LEADERBOARD UPDATE STARTED");
    
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istTime = new Date(now.getTime() + istOffset);
    const hour = istTime.getUTCHours();
    
    console.log(`IST Hour: ${hour}`);
    
    const snapshot = await db.ref("leaderboard").once("value");
    const users = snapshot.val() || {};
    const todayKey = now.toISOString().split("T")[0];
    const updates = {};
    
    // Check if weekly reset is needed
    let resetWeek = await shouldResetWeek(now);
    
    if (resetWeek) {
      await saveTop3BeforeReset(users);
      updates["_global/lastWeeklyReset"] = now.toISOString();
    }

    await manageOnlineStates(users, hour, updates);

    let realUserCount = 0;
    let fakeActiveCount = 0;
    let fakeInactiveCount = 0;
    let processedCount = 0;
    let changedCount = 0;

    console.log("LOG C → resetWeek inside user loop =", resetWeek);
    
    for (const [uid, user] of Object.entries(users)) {
      try {
        const category = getUserCategory(user);
        
        // ============================================================
        // HANDLE REAL USERS (from mobile app)
        // ============================================================
        if (category === "real") {
          realUserCount++;

          if (resetWeek) {
            // ✅ WEEKLY RESET: Clear everything for new week
            console.log(`[RESET] Applying weekly reset to REAL user ${uid}`);
            
            updates[`leaderboard/${uid}/history`] = {};
            updates[`leaderboard/${uid}/weekHours`] = 0;
            updates[`leaderboard/${uid}/score`] = 0;
            updates[`leaderboard/${uid}/todayHours`] = 0;
            
            // ✅ CRITICAL: Set reset flag so Python app knows to start new week
            updates[`leaderboard/${uid}/weeklyResetAt`] = now.toISOString();
            
            // ✅ Update lastUpdate so app knows data changed
            updates[`leaderboard/${uid}/lastUpdate`] = now.toISOString();
            
            changedCount++;
          } else {
            // ✅ NORMAL OPERATION: Let Python app control the data
            // Firebase should NOT modify real user data between resets
            // Just update the timestamp to acknowledge we've seen their data
            
            const lastUpdate = user.lastUpdate ? new Date(user.lastUpdate) : new Date(0);
            const minsSinceUpdate = (now - lastUpdate) / 1000 / 60;
            
            // Only update lastUpdate if app recently sent data (within 10 minutes)
            // This prevents Firebase from "touching" stale users
            if (minsSinceUpdate < 10) {
              updates[`leaderboard/${uid}/lastUpdate`] = now.toISOString();
            }
            
            // ✅ IMPORTANT: Don't modify history, weekHours, todayHours, etc.
            // The Python app is the source of truth for real users!
          }
          
          continue; // Move to next user
        }
        
        // ============================================================
        // HANDLE FAKE INACTIVE USERS (display only, never update)
        // ============================================================
        if (category === "fake_inactive") {
          fakeInactiveCount++;
          if (resetWeek) {
            updates[`leaderboard/${uid}/history`] = {};
            updates[`leaderboard/${uid}/weekHours`] = 0;
            updates[`leaderboard/${uid}/score`] = 0;
            updates[`leaderboard/${uid}/todayHours`] = 0;
            updates[`leaderboard/${uid}/online`] = false;
            updates[`leaderboard/${uid}/status`] = "Offline";
            updates[`leaderboard/${uid}/isFakeInactive`] = true;
          }
          continue;
        }
        
        // ============================================================
        // HANDLE FAKE ACTIVE USERS (normal processing)
        // ============================================================
        fakeActiveCount++;
        processedCount++;
        
        const oldUser = {...user};
        let hasChanges = false;

        // Initialize performance profile if needed
        if (!user.perfType || !user.dailyTarget || !user.onlinePreference) {
          const profile = initializeUserProfile(uid);
          updates[`leaderboard/${uid}/perfType`] = profile.perfType;
          updates[`leaderboard/${uid}/dailyTarget`] = profile.dailyTarget;
          updates[`leaderboard/${uid}/studyPace`] = profile.studyPace;
          updates[`leaderboard/${uid}/onlinePreference`] = profile.onlinePreference;
          Object.assign(user, profile);
          hasChanges = true;
        }

        // Weekly reset for fake users
        if (resetWeek) {
          user.history = {};
          updates[`leaderboard/${uid}/history`] = {};
          updates[`leaderboard/${uid}/weekHours`] = 0;
          updates[`leaderboard/${uid}/score`] = 0;
          updates[`leaderboard/${uid}/todayHours`] = 0;
          hasChanges = true;
          continue;
        }

        // Calculate time delta
        const lastUpdate = user.lastUpdate ? new Date(user.lastUpdate) : now;
        let dt = (now - lastUpdate) / 1000;
        dt = clamp(dt, 0, 350);
        
        const history = user.history || {};
        let seconds = history[todayKey] || 0;
        const oldSeconds = seconds;

        // Update study time if user is online
        if (user.online) {
          const todayHours = seconds / 3600;
          const dailyTarget = user.dailyTarget || 5;
          
          if (todayHours < dailyTarget) {
            const studyPace = user.studyPace || 0.8;
            let gain = dt * studyPace;
            gain *= (0.95 + Math.random() * 0.1);
            if (user.perfType === "low" && Math.random() < 0.3) gain *= 0.7;
            if (user.perfType === "top" && Math.random() < 0.3) gain *= 1.1;
            seconds += gain;
            const maxSeconds = dailyTarget * 3600;
            seconds = Math.min(seconds, maxSeconds);
          }
        }

        // Update history if seconds changed
        if (Math.floor(seconds) !== Math.floor(oldSeconds)) {
          history[todayKey] = Math.floor(seconds);
          updates[`leaderboard/${uid}/history/${todayKey}`] = Math.floor(seconds);
          hasChanges = true;
        }

        // Calculate aggregates
        const todayHours = parseFloat((seconds / 3600).toFixed(2));
        const last7Days = Object.keys(history).sort().slice(-7).map((d) => history[d] || 0);
        const weekHours = parseFloat((last7Days.reduce((a, b) => a + b, 0) / 3600).toFixed(2));
        const score = Math.floor(weekHours * 100);
        const status = user.online ? "Online" : "Offline";

        // Write only changed values
        if (oldUser.todayHours !== todayHours) {
          updates[`leaderboard/${uid}/todayHours`] = todayHours;
          hasChanges = true;
        }
        if (oldUser.weekHours !== weekHours) {
          updates[`leaderboard/${uid}/weekHours`] = weekHours;
          hasChanges = true;
        }
        if (oldUser.score !== score) {
          updates[`leaderboard/${uid}/score`] = score;
          hasChanges = true;
        }
        if (oldUser.status !== status) {
          updates[`leaderboard/${uid}/status`] = status;
          hasChanges = true;
        }

        // Always update lastUpdate timestamp
        const newLastUpdate = now.toISOString();
        if (oldUser.lastUpdate !== newLastUpdate) {
          updates[`leaderboard/${uid}/lastUpdate`] = newLastUpdate;
          hasChanges = true;
        }

        if (hasChanges) changedCount++;

      } catch (err) {
        console.error(`Error processing user ${uid}:`, err);
      }
    }

    // Write all updates at once
    if (Object.keys(updates).length > 0) {
      await db.ref().update(updates);
      console.log(`✅ Delta updates: ${Object.keys(updates).length} field changes`);
    }

    console.log(
      `[${now.toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}] ` +
      `REAL: ${realUserCount}, FAKE_ACTIVE: ${fakeActiveCount}, FAKE_INACTIVE: ${fakeInactiveCount}. ` +
      `Processed: ${processedCount}, Changed: ${changedCount}, Reset: ${resetWeek}`
    );

    return null;
  } catch (error) {
    console.error("❌ Leaderboard update error:", error);
    return null;
  }
}

async function sendTelegramReport(chatId, pdfBase64, filename) {
  const TELEGRAM_BOT_TOKEN = getTelegramToken();

  if (!TELEGRAM_BOT_TOKEN) {
    console.error('Telegram bot token not configured');
    return false;
  }

  if (!chatId || !pdfBase64) {
    return false;
  }

  try {
    const formData = new FormData();
    formData.append('chat_id', chatId);
    formData.append('document', Buffer.from(pdfBase64, 'base64'), {
      filename: filename || 'Study_Report.pdf',
    });

    const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument`;
    const response = await axios.post(url, formData, {
      headers: formData.getHeaders(),
      maxContentLength: Infinity,
      maxBodyLength: Infinity,
    });

    return response.data.ok === true;
  } catch (error) {
    console.error(`Failed to send report to ${chatId}:`, error.message);
    return false;
  }
}

async function processStudyReports(istTime) {
  const todayKey = istTime.toISOString().slice(0, 10);
  const snapshot = await db.ref('studyReports').once('value');

  if (!snapshot.exists()) {
    console.log('ℹ️ No study reports queued for dispatch');
    return { sent: 0, cleaned: 0 };
  }

  const reports = snapshot.val();
  const updates = {};
  let sentCount = 0;
  let cleanedCount = 0;

  for (const [uid, userReports] of Object.entries(reports)) {
    if (!userReports || typeof userReports !== 'object') continue;

    for (const [reportDateKey, reportData] of Object.entries(userReports)) {
      if (!reportData) {
        updates[`studyReports/${uid}/${reportDateKey}`] = null;
        cleanedCount++;
        continue;
      }

      const reportDate = reportData.reportDate || reportDateKey;
      if (reportDate !== todayKey) continue;

      const pdfBase64 = reportData.pdfBase64 || reportData.pdf;
      const chatId = reportData.telegramChatId || reportData.chatId;

      if (!pdfBase64 || !chatId) {
        updates[`studyReports/${uid}/${reportDateKey}`] = null;
        cleanedCount++;
        continue;
      }

      const sent = await sendTelegramReport(chatId, pdfBase64, `Study_Report_${reportDate}.pdf`);
      if (sent) {
        sentCount++;
        updates[`studyReports/${uid}/${reportDateKey}`] = null;
        updates[`_reportLogs/${uid}/${reportDate}`] = {
          sentAt: istTime.toISOString(),
          via: 'auto_scheduler',
        };
      }
    }
  }

  if (Object.keys(updates).length > 0) {
    await db.ref().update(updates);
  }

  console.log(`📤 Auto study reports sent: ${sentCount}, cleaned: ${cleanedCount}`);
  return { sent: sentCount, cleaned: cleanedCount };
}

async function runNotificationCheck() {
  try {
    console.log('\n🔔 NOTIFICATION CHECK STARTED');

    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istTime = new Date(now.getTime() + istOffset);
    const currentTime = istTime.toISOString().slice(11, 16);
    
    console.log(`⏰ Current IST time: ${currentTime}`);
    
    const groupsSnapshot = await db.ref('studyGroups').once('value');

    if (!groupsSnapshot.exists()) {
      console.log('❌ No groups found');
    }

    const groups = groupsSnapshot.val() || {};
    let notificationsSent = 0;
    let plansChecked = 0;
    let sessionsChecked = 0;
    let reportSummary = { sent: 0, cleaned: 0 };
    
    for (const [groupId, groupData] of Object.entries(groups)) {
      const groupName = groupData.metadata?.name || 'Study Group';
      const plans = groupData.plans || {};
      
      for (const [planId, planData] of Object.entries(plans)) {
        plansChecked++;
        const planName = planData.name || 'Study Plan';
        const enrolledMembers = planData.enrolled_members || [];
        
        if (enrolledMembers.length === 0) continue;
        
        let sessions = [];
        try {
          const fileData = JSON.parse(planData.file_data || '{}');
          sessions = fileData.sessions || [];
        } catch (e) {
          continue;
        }
        
        for (let i = 0; i < sessions.length; i++) {
          const session = sessions[i];
          sessionsChecked++;
          
          let sessionName, startTime;
          
          if (Array.isArray(session) && session.length >= 2) {
            sessionName = session[0];
            startTime = session[1];
          } else if (typeof session === 'object') {
            sessionName = session.name || 'Session';
            startTime = session.start_time || '';
          } else {
            continue;
          }
          
          const sessionDateTime = new Date(istTime);
          const [sessionHour, sessionMinute] = startTime.split(':').map(Number);
          sessionDateTime.setHours(sessionHour, sessionMinute, 0, 0);
          const timeDiff = (istTime - sessionDateTime) / 1000 / 60;

          if (timeDiff >= 0 && timeDiff < 5) {
            const notificationKey = `${groupId}_${planId}_${i}_${startTime}`;
            const lastSentRef = await db.ref(`_notifications/lastSent/${notificationKey}`).once('value');
            const lastSent = lastSentRef.val();
            
            if (lastSent) {
              const lastSentTime = new Date(lastSent);
              const hoursSinceLastSent = (istTime - lastSentTime) / 1000 / 60 / 60;
              if (hoursSinceLastSent < 12) continue;
            }
            
            console.log(`🔥 SESSION MATCH: ${sessionName} at ${startTime}`);
            
            for (const memberId of enrolledMembers) {
              try {
                const memberSnapshot = await db.ref(`studyGroups/${groupId}/members/${memberId}`).once('value');
                const memberData = memberSnapshot.val();
                if (!memberData) continue;
                
                const telegramId = memberData.telegram_chat_id;
                
                if (telegramId) {
                  const message = 
                    `⏰ <b>Session Starting Now!</b>\n\n` +
                    `<b>Group:</b> ${groupName}\n` +
                    `<b>Plan:</b> ${planName}\n` +
                    `<b>Session:</b> ${sessionName}\n` +
                    `<b>Time:</b> ${startTime}\n\n` +
                    `📚 Your study session is starting!\n` +
                    `💪 Please join now and get ready to focus!`;
                  
                  const sent = await sendTelegramMessage(telegramId, message);
                  if (sent) notificationsSent++;
                }
              } catch (error) {
                console.error(`Error sending to ${memberId}:`, error.message);
              }
            }
            
            await db.ref(`_notifications/lastSent/${notificationKey}`).set(istTime.toISOString());
          }
        }
      }
    }

    if (isWithinReportWindow(istTime)) {
      try {
        reportSummary = await processStudyReports(istTime);
      } catch (error) {
        console.error('Auto report dispatch error:', error.message);
      }
    } else {
      console.log('📭 Outside auto-report window, skipping dispatch check');
    }

    console.log(`📊 Plans: ${plansChecked}, Sessions: ${sessionsChecked}, Sent: ${notificationsSent}, Reports: ${reportSummary.sent}`);
    return null;

  } catch (error) {
    console.error('Notification check error:', error);
    return null;
  }
}
/**
 * Send Telegram message
 */
async function sendTelegramMessage(chatId, message) {
    const TELEGRAM_BOT_TOKEN = getTelegramToken();
    
    if (!TELEGRAM_BOT_TOKEN) {
        console.error('Telegram bot token not configured');
        return false;
    }
    
    try {
        const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
        const response = await axios.post(url, {
            chat_id: chatId,
            text: message,
            parse_mode: 'HTML'
        });
        return response.data.ok;
    } catch (error) {
        console.error(`Failed to send to ${chatId}:`, error.message);
        return false;
    }
}

