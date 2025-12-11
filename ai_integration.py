"""
AI Integration for Study Timer
Creates ONE TEXT FILE with all data that you can copy-paste to AI

Output: One comprehensive text file with all your study data
"""

import json
import os
import csv
from datetime import datetime
from pathlib import Path

# Import your existing AppPaths system
try:
    from config_paths import app_paths
    print("[OK] Using your AppPaths configuration system")
except ImportError:
    print("⚠️  Could not import config_paths. Make sure it's in the same folder!")
    import sys
    sys.exit(1)

# Folders
SOURCE_FOLDER = Path(app_paths.appdata_dir)
AI_DATA_FOLDER = SOURCE_FOLDER / 'ai_data_feed'

# Files to SKIP (sensitive data)
SKIP_FILES = [
    '.integrity',
    '.trial_salt',
    '.trial_data',
    'app_license.dat',
    'app_license',
    'payment_status.json',
    'payment_status',
    'license.salt',
    '.st_backup',
    '.time_check',
    'last_runrate.jpg',
]


def should_skip_file(filename):
    """Check if file should be skipped"""
    name_lower = filename.lower()
    
    # Skip sensitive files
    for skip in SKIP_FILES:
        if skip.lower() in name_lower:
            return True
    
    # Skip image files
    if filename.endswith(('.jpg', '.png', '.jpeg', '.gif', '.bmp')):
        return True
    
    return False


def read_file_content(file_path):
    """
    Read file content based on type
    Returns tuple: (content, file_type)
    """
    
    filename = file_path.name
    
    try:
        # JSON files
        if filename.endswith('.json') or '.' not in filename:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            return json.dumps(content, indent=2, ensure_ascii=False), "JSON"
        
        # CSV files
        elif filename.endswith('.csv'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content, "CSV"
        
        # Text files
        elif filename.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content, "TEXT"
        
        # Other files - try as text
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content, "OTHER"
    
    except Exception as e:
        return f"[Error reading file: {e}]", "ERROR"


def create_comprehensive_data_file():
    """
    Create ONE comprehensive text file with ALL data
    This file can be copy-pasted to AI
    """
    
    print(f"\n📂 Reading files from: {SOURCE_FOLDER}\n")
    
    # Create ai_data_feed folder
    AI_DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    
    # Start building the comprehensive file
    output = []
    
    # Header
    output.append("=" * 80)
    output.append("STUDY TIMER - COMPLETE DATA FOR AI ANALYSIS")
    output.append("=" * 80)
    output.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output.append(f"Source: {SOURCE_FOLDER}")
    output.append("=" * 80)
    output.append("")
    
    # Read all files
    processed_files = []
    skipped_files = []
    
    for item in sorted(SOURCE_FOLDER.iterdir()):
        # Skip folders
        if item.is_dir():
            continue
        
        filename = item.name
        
        # Skip sensitive files
        if should_skip_file(filename):
            skipped_files.append(filename)
            continue
        
        # Read file
        print(f"📄 Reading: {filename}")
        content, file_type = read_file_content(item)
        
        # Add to output
        output.append("")
        output.append("=" * 80)
        output.append(f"FILE: {filename}")
        output.append(f"TYPE: {file_type}")
        output.append(f"SIZE: {item.stat().st_size} bytes")
        output.append("=" * 80)
        output.append("")
        output.append(content)
        output.append("")
        
        processed_files.append(filename)
    
    # Footer with file summary
    output.append("")
    output.append("=" * 80)
    output.append("FILE SUMMARY")
    output.append("=" * 80)
    output.append(f"Total files processed: {len(processed_files)}")
    output.append(f"Files skipped (sensitive): {len(skipped_files)}")
    output.append("")
    output.append("Processed files:")
    for f in processed_files:
        output.append(f"  ✅ {f}")
    
    if skipped_files:
        output.append("")
        output.append("Skipped files:")
        for f in skipped_files:
            output.append(f"  ⏭️  {f}")
    
    output.append("")
    output.append("=" * 80)
    output.append("END OF DATA")
    output.append("=" * 80)
    
    # Save to file
    output_text = "\n".join(output)
    output_file = AI_DATA_FOLDER / "ALL_DATA_FOR_AI.txt"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(output_text)
    
    print(f"\n✅ Created: ALL_DATA_FOR_AI.txt")
    print(f"   Size: {len(output_text)} characters")
    
    return output_file, processed_files, skipped_files


def create_ai_prompt():
    """
    Create the prompt/instructions for AI (embedded verbatim).
    """
    prompt = """EXAM SCHEDULE FOR EXAMPLE:

⚙ SSC JE Electrical Engineering – Paper 1 (Objective Type)

Total Marks: 200  Duration: 2 Hours
Sections:

1. General Intelligence & Reasoning (50 marks)


2. General Awareness (50 marks)


3. Electrical Engineering (100 marks)




---

🧠 1. General Intelligence & Reasoning

Analogies, similarities & differences

Space visualization, problem-solving, analysis, judgment, decision-making

Visual memory, discriminating observation

Relationship concepts, arithmetical reasoning

Verbal & figure classification

Arithmetical number series

Non-verbal reasoning, syllogisms, etc.



---

🌍 2. General Awareness

Current affairs (national + international)

Indian polity & constitution

Geography, history, culture

Economics, scientific research, environmental issues

Everyday science & technology (esp. power, renewable energy, etc.)



---

⚡ 3. Electrical Engineering (Core Subject)

A. Basic Concepts

Concepts of current, voltage, power, energy, and their units

Ohm’s law, Kirchhoff’s laws

AC & DC quantities, RMS, average values, form & peak factors


B. Circuit Law & Network Theorems

Superposition, Thevenin, Norton, and Maximum power transfer theorems

Mesh & nodal analysis

Star-delta transformations


C. AC Fundamentals

Single-phase and three-phase systems

Power factor, reactive power, apparent power

Resonance, impedance, and admittance


D. Electrical Machines

DC Machines: Construction, EMF equation, characteristics, applications

Transformers: Types, EMF equation, losses, efficiency, testing (OC & SC)

AC Machines: Alternators, synchronous motors, induction motors (1-phase & 3-phase), torque-speed characteristics, starting & speed control


E. Measurements & Measuring Instruments

Measurement of current, voltage, power, energy, frequency

Use of ammeters, voltmeters, wattmeters, energy meters

Errors, accuracy, and calibration


F. Electrical Power Systems

Generation (thermal, hydro, nuclear, renewable)

Transmission & distribution systems

Line parameters, efficiency & regulation of transmission lines

Types of cables, insulators, and power factor improvement


G. Estimation & Costing

Basics of estimation and wiring systems

Earthing and lighting schemes

Determination of material cost, labor, and total estimation


H. Basic Electronics

Semiconductor theory, diodes, transistors, amplifiers, oscillators

Rectifiers (half-wave, full-wave, bridge)

OP-AMP basics, logic gates, digital fundamentals


ABOVE DETAILS ARE EXAMPLE FOR TEACH AI THAT HOW TO HANDLE USER WITH THEM EXAMINATION

1) on profile setup below details will be taken from users
name
exam_exam
exam date
language

1) 1st chat:

after profile setup cmplete Ai should show this info:   hi, (user name) i am your Ai coach, it seems your preparing for [exam] , [should tell some words about them intrest on that exam], [should tell about them current time period to preparing that exam (calulate time period by user input data(exam date))response type base on 1)if they have enough time period
2)if they dont have enough time period then should reaponse accoringly like for exxample : you have short period; but dont worry we definity crack your exam (should respond like motivation give hope them) then should ask them [can i create scheduled study plan for you{this msg should ask them repeatedly untill they create themslves any plan or you make any plan}]

2)listen user input:

two possibilities:
*)they should ask about create plan
*)or ask anything else 

if they ask anything else about them current status of preparation or mindset, feel bad about exam, or looking for right material, [your choice you can motivate them as a coach make interaction with time and can motivate and give some importnt more weightage most ask pyp material if they ask, if they dont make study plan yet then give them suggestion them to make study plan according them input / conversation. 

if they ask for plan directly then ask them per day study hours & exact time duration after they enter study duration then you should make list of plan like below (see above ssc je electrical syllabus)

*)PLAN 1 overall plan (should have topics related)
--------------------------------------------------------------------

session 1. General Intelligence & Reasoning      start/end time break time
session 2. General Awareness    start/end time  break time
sssion 3. Electrical Engineering   start/end time  break time

*)PLAN 2 (🧠  General Intelligence & Reasoning)
------------------------------------------------------------------

sssion 1. Analogies, similarities & differences     ( start/end time  break time)

sess 2. Space visualization, problem-solving, analysis, judgment, decision-making   (start/end time  break time)

sess 3. Visual memory, discriminating observation  ( start/end time  break time)

sess 4. Relationship concepts, arithmetical reasoning  ( start/end time  break time)

sess 5. Verbal & figure classification ( start/end time  break time)

sess 6. Arithmetical number series   ( start/end time  break time)

sess 7. Non-verbal reasoning, syllogisms, etc.  ( start/end time  break time)

*)PLAN 3 (🌍  General Awareness)
-------------------------------------------------

sess 1. Current affairs (national + international)  ( start/end time  break time)

sess 2. Indian polity & constitution  ( start/end time  break time)

sess 3. Geography, history, culture  ( start/end time  break time)

sess 4. Economics, scientific research, environmental issues  ( start/end time  break time)

sess 5. Everyday science & technology (esp. power, renewable energy, etc.)  ( start/end time  break time)

*) PLAN 4 (Electrical Engineering (Core Subject))
------------------------------------------------------------

sess 1. Basic Concepts  ( start/end time  break time)

sess 2. Circuit Law & Network Theorems  ( start/end time  break time)
 
sess 3. AC Fundamentals  ( start/end time  break time)

sess 4. Electrical Machines  ( start/end time  break time)

sess 5. Measurements & Measuring Instruments  ( start/end time  break time)

sess 6. Electrical Power Systems  ( start/end time  break time)

sess 7. Estimation & Costing  ( start/end time  break time)

IF THEY ASK FOR ANY PARTICULAR TOPIC THEN SHOULD CREATE PLAN FOR THAT PARTICULAR TOPIC 
for example: if they ask for plan about BASIC CONCEPT then should breakdown basic concept further like below

PLAN (BASIC CONCEPT)
--------------------------------

sess 1. Concepts of current, voltage, power, energy, and their units   ( start/end time  break time)

sess 2. Ohm’s law, Kirchhoff’s laws   ( start/end time  break time)

sess 3. AC & DC quantities, RMS, average values, form & peak factors   ( start/end time  break time)

And my software only can recognize this structure(see below example) of plans. so create all plans like this structure

here is exact structure that can my software recognize (having three plans ,default,wert,sde)

{
  "Default": [
    [
      "GI & Reasoning 1",
      "07:00",
      "08:30",
      "08:30-08:42"
    ],
    [
      "General Science 1",
      "08:42",
      "10:42",
      "10:42-11:02"
    ],
    [
      "Current Affairs 1",
      "11:02",
      "12:32",
      "12:32-12:44"
    ],
    [
      "GI & Reasoning 2",
      "12:44",
      "14:14",
      "14:14-14:29"
    ],
    [
      "General Science 2",
      "14:29",
      "16:59",
      "16:59-17:19"
    ],
    [
      "General Science 3",
      "17:19",
      "20:19",
      "20:19-20:39"
    ],
    [
      "Static GK",
      "20:39",
      "22:39",
      "No Break"
    ],
    [
      "Planning Session",
      "22:39",
      "23:39",
      "No Break"
    ]
  ],
  "wert": [
    [
      "tamil",
      "09:00",
      "11:00",
      "No Break"
    ],
    [
      "maths",
      "11:00",
      "13:00",
      "No Break"
    ],
    [
      "science",
      "13:00",
      "15:00",
      "No Break"
    ]
  ],
  "sde": [
    [
      "physics",
      "09:00",
      "11:00",
      "11:00-11:45"
    ],
    [
      "tamil",
      "21:00",
      "23:00",
      "No Break"
    ],
    [
      "english",
      "23:00",
      "01:00",
      "No Break"
    ]
  ]
}SO ALL PLANS SHOULD BE MADE LIKE THIS FORMAT ,  
IMPORTANT:
SHOULD SAVE THESE SHEDULE ON PLANS.JSON IN APPDATA then only it can reflect on app
SESSION NAME LOGIC : no one session name should not exceed 2 words 
STUDY DURATION ALLOCATE LOGIC: main most weightage topic should have more study duration (time should be allocate according session weightage percentage) for example having 3 sessions like machine,power electronics,UEE, out of this three session machine is 60 percent weightage for my ssc je exaam so machine should have more study duration from GIVEN TIME
BREAK DURATION ALLOCATION LOGIC: for every one hour there should be 10 mins break and FOR BREAK FAST : give 30mins break btw 7am to 9 am FOR LUNCH BREAK : give 30mins break btw 12:30 pm to 2 pm FOR DINNER : give 30mins break btw 7pm to 9pm. 	
ALSO ALL SHEDULE MUST CONTAIN REVISION SESSION : revision strategy and timing is your wish you can refer online or any principal for revision.
ALSO MY SOFTWARE WILL RECOGNZE TAMIL 1, TAMIL 2 INTO "TAMIL" SO IF ANY SESSION SPLIT BTW BREAK THEN MAKE IT LIKE 1,2,3
 """
    return prompt


def generate_ai_analysis():
    """
    MAIN FUNCTION
    Creates everything needed for AI analysis
    """
    
    print("\n" + "="*80)
    print("🤖 AI DATA PREPARATION - SINGLE FILE METHOD")
    print("="*80)
    
    # Step 1: Create comprehensive data file
    print("\n📋 Step 1: Reading and combining all files...\n")
    data_file, processed, skipped = create_comprehensive_data_file()
    
    # Step 2: Create AI prompt
    print("\n📋 Step 2: Creating AI prompt...")
    prompt = create_ai_prompt()
    
    # Combine prompt with data reference
    full_prompt = prompt + "\n(Now paste the content from ALL_DATA_FOR_AI.txt below this prompt)\n"
    
    prompt_file = AI_DATA_FOLDER / "AI_PROMPT.txt"
    with open(prompt_file, 'w', encoding='utf-8') as f:
        f.write(full_prompt)
    
    print(f"✅ Created: AI_PROMPT.txt")
    
   
    
    # Success summary
    print(f"\n" + "="*80)
    print("✅ SUCCESS!")
    print("="*80)
    print(f"\n📁 Files saved in:")
    print(f"   {AI_DATA_FOLDER}")
    print(f"\n📄 Created files:")
    print(f"   1. ALL_DATA_FOR_AI.txt  ← Your complete data (copy-paste to AI)")
    print(f"   2. AI_PROMPT.txt        ← Instructions for AI")
   
    print(f"\n📊 Statistics:")
    print(f"   • Files processed: {len(processed)}")
    print(f"   • Files skipped: {len(skipped)} (sensitive data)")
    print(f"\n🎯 NEXT STEPS:")
    print(f"   1. Open INSTRUCTIONS.txt and read it")
    print(f"   2. Copy AI_PROMPT.txt content")
    print(f"   3. Copy ALL_DATA_FOR_AI.txt content")
    print(f"   4. Paste both to ChatGPT/Claude")
    print(f"   5. Get your analysis!")
    
    print("\n" + "="*80)
    
    # Try to open folder
    try:
        os.startfile(str(AI_DATA_FOLDER))
        print("📂 Folder opened automatically!")
    except:
        print(f"\n💡 Open manually: %APPDATA%\\StudyTimer\\ai_data_feed")
    
    return str(AI_DATA_FOLDER)


if __name__ == "__main__":
    """
    Run this: python ai_integration.py
    """
    
    print("🧪 AI Integration - Single File Method\n")
    
    result = generate_ai_analysis()
    
    if result:
        print(f"\n✅ Done! Read INSTRUCTIONS.txt to continue!")
    else:
        print("\n❌ Failed! Check errors above.")