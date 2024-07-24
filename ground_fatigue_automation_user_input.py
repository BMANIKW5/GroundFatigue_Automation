from ground_fatigue_automation_main import *

aircraft_type = "A321"
ADS_path="/projects/ATLAS/p/E271L4M1/TLM/FLAN/MDT_AC/MZ/v03/MDT_A321neo_ACF_STEP41_+1t_TLM_v03.ads"
Comp_applicabilty="/projects/ATLAS/p/E271L4M1/TLM/GROUND/study/Internship_2024/comp_applicability/test1.csv"
batman_config = "/projects/ATLAS/p/E271L4M1/TLM/GROUND/study/Internship_2024/batman_config"
soldyn_config = "/projects/ATLAS/p/E271L4M1/TLM/GROUND/study/Internship_2024/soldyn_config"
outpur_dir="/projects/ATLAS/p/E271L4M1/TLM/GROUND/study/Internship_2024/output_dir"
BatmanFlag = 1
SoldynFlag = 1
SFBumpsFlag = 1

Soldyn_execFlag = 0
Batman_execFlag = 1

## Dont touch the below code.
inputs = [BatmanFlag, SoldynFlag, aircraft_type, ADS_path, Comp_applicabilty, batman_config,soldyn_config,outpur_dir,SFBumpsFlag,Soldyn_execFlag,Batman_execFlag]
obj = batman(inputs)
obj.run()


