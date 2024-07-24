import re                               
import pandas as pd        
import xml.etree.ElementTree as ET
from xml.dom import minidom  
import os
from lxml import etree
import copy
import logging
import subprocess



class batman:

    def __init__(self, inputs):
        
        self.__output_dir = inputs[7]
        filenames = os.listdir(self.__output_dir)
        log_filenames = []
        for i in range(len(filenames)):
            log_check = pd.Series(filenames[i]).str.contains(".log",flags=re.IGNORECASE,regex=True)[0]
            if log_check:
                log_filenames.append(filenames[i])
       
        maxi = 0
        for i in range(len(log_filenames)):
            num = re.findall(r"\d+", str(log_filenames[i]), re.DOTALL)[0]
            if int(num) > int(maxi):
                maxi = num
        
        maxi = int(maxi)+1
        
        self.__log_path = self.__output_dir+f"/log_file_{str(maxi)}.log"
        self.__logger = logging.getLogger(os.getlogin())
        self.__logger.setLevel(logging.INFO)
        self.__handler = logging.FileHandler(self.__log_path)
        self.__formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        for hdlr in self.__logger.handlers[:]:  # remove the existing file handlers
            if isinstance(hdlr,logging.FileHandler):
                self.__logger.removeHandler(hdlr)
        
        self.__handler.setFormatter(self.__formatter)
        self.__logger.addHandler(self.__handler)
        
        self.__BatmanFlag = inputs[0]
        if self.__BatmanFlag !=0 and self.__BatmanFlag != 1:
            raise Exception("Please check the BatmanFlag.")
            
        self.__SoldynFlag = inputs[1]
        if self.__SoldynFlag !=0 and self.__SoldynFlag != 1:
            self.__logger.error("Please check the SoldynFlag.")
            raise Exception("Please check the SoldynFlag.")
         
        
        self.__aircraft_type = inputs[2]
        self.__single_aisle_aircraft = ["A318", "A319", "A320", "A321"]
        if self.__aircraft_type not in self.__single_aisle_aircraft:
            self.__logger.error("Code is mainly for single aisle aircraft")
            raise Warning("Code is mainly for single aisle aircraft")
        
        self.__ads_path = inputs[3]
        self.__comp_applicabilty = inputs[4]
        self.__batman_config = inputs[5]
        self.__soldyn_config = inputs[6]
        
        self.__SFBumpsFlag = inputs[8]
        self.__Soldyn_execFlag = inputs[9]
        self.__Batman_execFlag = inputs[10]
        
        self.__batman_tempFlag = 1
        self.__soldyn_tempFlag = 1
        self.__bumps_temp_FHT_Flag = 1
        self.__bumps_temp_FHR_Flag = 1
        self.__bumps_temp_FLR_Flag = 1
        self.__mlg_touch_temp_Flag = 1
        self.__bumps_1g_temp_Flag = 1
        
        self.__soldyn_smry_tempFlag = 0
        self.__batman_smry_tempFlag = 0
    
        
        self.__soldyn_exec_path_list = []
        self.__batman_exec_path_list = []

        try:
            with open(self.__ads_path,'r') as file:
                self.__file_data = file.read()
                self.__logger.info(self.__ads_path+ ' read successfully')
        except FileNotFoundError:
            self.__logger.error("Ads file not found. Please check the path or filename.")
            raise Exception("Ads file not found. Please check the path or filename.")

    def __split(self, definition_file, data):
        data_n = 0
        data_prev = data[0][1]
        for i in range(0, len(data)):
            if data[i][1] != data_prev:
                data_n += 1
            data_prev = data[i][1]
        data_part = []
        for j in range(0, data_n):
            pattern = definition_file + r"\["+str(j)+r"\].(.*?)\'"
            data_part.append(re.findall(pattern, str(data)))
        return data_part

    def __SplitedTables(self):
        fmd = re.findall(r"(FMD\[(\d+)\].(.*?))\n", self.__file_data, re.DOTALL)
        self.__FMD_part = self.__split(r"FMD",fmd)

        events = re.findall(r"(Events\[(\d+)\].(.*?))\n", self.__file_data, re.DOTALL)
        self.__events_part = self.__split(r"Events",events)

        LCC_Def = re.findall(r"(LCCDef\[(\d+)\].(.*?))\n", self.__file_data, re.DOTALL)
        self.__LCC_Def_part = self.__split(r"LCCDef",LCC_Def)

        LL = re.findall(r"(LL\[(\d+)\].(.*?))\n", self.__file_data, re.DOTALL)
        self.__LL_part = self.__split(r"LL",LL)

        DataDict = re.findall(r"(DataDict\[(\d+)\].(.*?))\n", self.__file_data, re.DOTALL)
        self.__DataDict_part = self.__split(r"DataDict",DataDict)
        
    def __columns(self, column_def, data):
        column_data = []
        for i in range(0, len(data)):
            pattern = column_def+r"=(.*?)\'"
            column = re.findall(pattern,str(data[i]))
            if column == []:
                column_data.append('NaN')
            else:
                column_data.append(column[0])
        return column_data
    
    def __get_columns_names(self, data_part):
        column_names = []
        column_names_unique = []
        for i in range(0, len(data_part)):
            names = re.findall(r"(\w*)=",str(data_part[i]))
            column_names+=names
        for x in column_names:
            if x not in column_names_unique:
                column_names_unique.append(x)
        return column_names_unique
    
    def __definition_table(self, column_names, data_part):
        for i in range(0, len(column_names)):
            if i == 0:
                def_table = pd.DataFrame(self.__columns(column_names[0], data_part))
                def_table.rename(columns={0:column_names[0]},inplace=True)
            else:
                 def_table[column_names[i]] = self.__columns(column_names[i], data_part)
        try:
            def_table = def_table.sort_values(by=self.__segment_no_name).reset_index(drop=True)
        except:
            pass
        return def_table
    
    
    # Generates FMD, LCC_Def, LL, Events and data dict tables
    def __tables(self):
        self.__SplitedTables()
        self.__FMD_column_names = self.__get_columns_names(self.__FMD_part)
        self.__events_column_names = self.__get_columns_names(self.__events_part)
        self.__LCC_Def_column_names = self.__get_columns_names(self.__LCC_Def_part)
        self.__LL_column_names = self.__get_columns_names(self.__LL_part)
        self.__DataDict_column_names = self.__get_columns_names(self.__DataDict_part)
        
        self.__FMD_table = self.__definition_table(self.__FMD_column_names, self.__FMD_part)
        self.__events_table = self.__definition_table(self.__events_column_names, self.__events_part)
        self.__LCC_Def_table = self.__definition_table(self.__LCC_Def_column_names, self.__LCC_Def_part)
        self.__LL_table = self.__definition_table(self.__LL_column_names, self.__LL_part)
        self.__DataDict_table = self.__definition_table(self.__DataDict_column_names, self.__DataDict_part)
        
        self.__fmd_series = pd.Series(self.__FMD_column_names)
        self.__lcc_series = pd.Series(self.__LCC_Def_column_names)
        self.__segment_id_name = self.__fmd_series[self.__fmd_series.str.contains("segment_?id",flags=re.IGNORECASE)].tolist()[0]
        self.__mission_id_name = self.__fmd_series[self.__fmd_series.str.contains("mission_?id",flags=re.IGNORECASE)].tolist()[0]
        self.__event_id_name = self.__lcc_series[self.__lcc_series.str.contains("event_?id",flags=re.IGNORECASE)].tolist()[0]
        self.__segment_no_name = self.__fmd_series[self.__fmd_series.str.contains("segment_?no",flags=re.IGNORECASE)].tolist()[0]
        self.__segment_desc_name = self.__fmd_series[self.__fmd_series.str.contains("segment_?desc",flags=re.IGNORECASE)].tolist()[0]
        self.__applicability_name = self.__fmd_series[self.__fmd_series.str.contains("appli",flags=re.IGNORECASE)].tolist()[0]
        self.__phase_no_name = self.__lcc_series[self.__lcc_series.str.contains("phase",flags=re.IGNORECASE)].tolist()[0]
        self.__man_method_name = self.__lcc_series[self.__lcc_series.str.contains("man",flags=re.IGNORECASE)].tolist()[0]
    
        self.__LRC_name = self.__lcc_series[self.__lcc_series.str.contains("LRC_?name",flags=re.IGNORECASE)].tolist()
        self.__LRC_croref_name = self.__lcc_series[self.__lcc_series.str.contains("LRC_?croref",flags=re.IGNORECASE)].tolist()
        self.__LRE1d_file_name = self.__lcc_series[self.__lcc_series.str.contains("LRE1d_?file",flags=re.IGNORECASE)].tolist()
        self.__ELS_file_name = self.__lcc_series[self.__lcc_series.str.contains("ELS_?file",flags=re.IGNORECASE)].tolist()
        
        self.__GEOM_basic_file_name = self.__lcc_series[self.__lcc_series.str.contains("GEOM_?basic_?file",flags=re.IGNORECASE)].tolist()
        self.__GEOM_OS_file_name = self.__lcc_series[self.__lcc_series.str.contains("GEOM_?OS_?file",flags=re.IGNORECASE)].tolist()
        self.__LRTC_name = self.__lcc_series[self.__lcc_series.str.contains("LRTC_?File",flags=re.IGNORECASE)].tolist()
  
    
  
    def final_table_full(self):
        self.__tables()
        self.FMD_table = self.__FMD_table
        self.LCC_Def_table = self.__LCC_Def_table
  
        
        #ELS, LRC_name, LRC_croref, LRTC_file, LRE1d_file, ELS_file, GEOM_basic_file, GEOM_OS_file dropping these columns
        dropping_cols = [self.__GEOM_OS_file_name,self.__LRTC_name, self.__GEOM_basic_file_name, self.__ELS_file_name, self.__LRE1d_file_name, self.__LRC_croref_name, self.__LRC_name]
        for col in dropping_cols:
            if len(col)!= 0:
                if col[0] in self.LCC_Def_table.columns:
                    self.LCC_Def_table.drop(col[0], axis=1, inplace=True)
        one_more_drop_col = ['ELS']
        for col in one_more_drop_col:
            if col in self.LCC_Def_table.columns:
                self.LCC_Def_table.drop(col, axis=1, inplace=True)
      
   
        self.Events_table = self.__events_table
        self.LL_table = self.__LL_table
        self.DataDict_table = self.__DataDict_table
        self.__final_table = pd.merge(self.__LCC_Def_table,self.__FMD_table,on=self.__segment_id_name)
        return self.__final_table                                                                          

    def ground_table(self):
        self.final_table_full()
        id1 = max(self.FMD_table[self.FMD_table[self.__segment_desc_name].str.contains("rotation",flags=re.IGNORECASE)].index.tolist())
        id2 = min(self.FMD_table[self.FMD_table[self.__segment_desc_name].str.contains("touch",flags=re.IGNORECASE)].index.tolist())
        self.__fmd_ground_table = self.FMD_table.iloc[:id1+1][:]
        self.__fmd_ground_table = self.__fmd_ground_table.append(self.FMD_table.iloc[id2:][:])
        self.__fmd_ground_table = self.__fmd_ground_table.sort_values(by=self.__segment_no_name).reset_index(drop=True)
        imp_columns_from_fmd = ["ph\w+_?desc\w*","hld_?conf\w*","seg\w+_?desc\w*","seg\w+_?id","thr\w+_?cond\w*","net\w+_?tot\w*","mass","mass_?case","VCAS"]
        self.__fmd_column_names = []
        for i in range(0,len(imp_columns_from_fmd)):
            column_name = self.__fmd_ground_table.columns[self.__fmd_ground_table.columns.str.contains(imp_columns_from_fmd[i],flags=re.IGNORECASE,regex=True)]
            self.__fmd_column_names.append(column_name[0])
        imp_data_from_fmd = self.__fmd_ground_table[self.__fmd_column_names]
        self.__final_ground_table = pd.merge(self.LCC_Def_table,imp_data_from_fmd,on=self.__segment_id_name)
        columns = self.__final_ground_table.columns.tolist()
        new_columns = columns[0:6]+columns[-len(imp_columns_from_fmd):]+columns[6:-len(imp_columns_from_fmd)]
        self.__final_ground_table = self.__final_ground_table.reindex(columns=new_columns).drop_duplicates().sort_values(by=self.__segment_no_name).reset_index(drop=True)  

        self.__calc_column_names = []
        omit_names = [self.__applicability_name, self.__event_id_name, self.__mission_id_name, self.__phase_no_name, self.__segment_id_name, self.__segment_no_name, self.__man_method_name]
        for name in self.LCC_Def_table.columns:
            if name not in omit_names:
                self.__calc_column_names.append(name)
        return self.__final_ground_table
    
    def __final_ground(self):
        self.ground_table()
        flag = 0
        #pd.options.mode.copy_on_write = True
        pd.options.mode.chained_assignment = None
        event_codes = self.__final_ground_table[self.__event_id_name].str.replace('([+-]?\d+)$','',regex=True).fillna('')
        event_codes_num = self.__final_ground_table[self.__event_id_name].str.extract('([+-]?\d+)$',expand=False).fillna('').str.replace('+','p',regex=True).str.replace('-','m',regex=True)
        self.__final_ground_table['param_code'] = self.__final_ground_table[self.__mission_id_name] + '_'+self.__final_ground_table[self.__segment_id_name] + '_'+ event_codes + '_' + event_codes_num
        self.__final_ground_table['param_thrust_code'] = self.__final_ground_table['param_code'] + self.__final_ground_table['Thrust_Cond'] + '_Thrust'
        
        for name in self.__calc_column_names:
            if flag==0:
                flag=1
                self.__upd_table = self.__final_ground_table[self.__final_ground_table[name]!='NaN']
                self.__upd_table.loc[:,'param_value'] = self.__upd_table.loc[:,name]
                self.__upd_table.loc[:,'param_code'] = self.__upd_table['param_code'] + name

            else:
                temp = self.__final_ground_table[self.__final_ground_table[name]!='NaN']
                temp.loc[:,'param_value'] = temp.loc[:,name]
                temp.loc[:,'param_code'] = temp['param_code'] + name
                self.__upd_table = self.__upd_table.append(temp)
        self.__upd_table = self.__upd_table.sort_index()
        cols = list(self.__upd_table.columns)
        cols[-2], cols[-1] = cols[-1], cols[-2]
        self.__upd_table = self.__upd_table[cols]
        self.__upd_table.loc[:,'param_thrust_value'] = pd.to_numeric(self.__final_ground_table.loc[:,"NetThrust_Tot"])/2
        self.__upd_table.loc[:,'param_thrust_value'] =self.__upd_table.loc[:,'param_thrust_value'].astype('int')  #if you remove this line, float values of thrust will come.
        # towing calculation
        tow_push_part = self.__upd_table[self.__upd_table["Event_ID"].str.contains("tow|push",flags=re.IGNORECASE,regex=True)]
        tow_push_part.loc[:,"param_value"] = pd.to_numeric(tow_push_part["param_value"])*(9.806/10)*pd.to_numeric(tow_push_part["Mass"])   
        self.__upd_table.loc[tow_push_part.index] = tow_push_part

        # 1g rotation calculation
        rot_1g_part = self.__upd_table[self.__upd_table["Segment_Desc"].str.contains("rotation",flags=re.IGNORECASE,regex=True)]
        rot_1g_part = rot_1g_part[rot_1g_part["Event_ID"].str.contains("1g",flags=re.IGNORECASE,regex=True)]
        rot_1g_part.loc[:,"param_value"] = pd.to_numeric(rot_1g_part["param_value"])*0.5
        self.__upd_table.loc[rot_1g_part.index] = rot_1g_part

        # incremental rotation calculation
        rot_incre_part = self.__upd_table[self.__upd_table["Segment_Desc"].str.contains("rotation",flags=re.IGNORECASE,regex=True)]
        rot_incre_part = rot_incre_part[rot_incre_part["Event_ID"].str.contains("rot",flags=re.IGNORECASE,regex=True)]
        rot_incre_part.loc[:,"param_value"] = pd.to_numeric(rot_incre_part["param_value"])*0.25*(9.806/10)*pd.to_numeric(rot_incre_part["Mass"])
        self.__upd_table.loc[rot_incre_part.index] = rot_incre_part

        # prelift dumping calculation
        pre_dump_pattern = '(?=.*before)(?=.*dump)'
        pre_dump_part = self.__upd_table[self.__upd_table["Segment_Desc"].str.contains(pre_dump_pattern,flags=re.IGNORECASE,regex=True)]
        pre_dump_part.loc[:,"param_value"] = pd.to_numeric(pre_dump_part["param_value"])/2
        self.__upd_table.loc[pre_dump_part.index] = pre_dump_part
        
        self.__upd_table.loc[:,"param_code"] = self.__upd_table.loc[:,"param_code"].str.replace('"', "'")
        
        
    # Grouping 
    
    def __grouping(self):
        try:
            with open(self.__comp_applicabilty,'r') as file:
                test_csv = pd.read_csv(file)
        except FileNotFoundError:
            self.__logger.error("Compatibility file not found. Please check the path or filename.")
            raise Exception("Compatibility file not found. Please check the path or filename.")
        
        self.__final_ground()
        
        groups = test_csv["Comp_ID"].tolist()
        grouped_tables_list = []
        index_numbers = []
        
        for i in range(0,len(groups)):
            if groups[i] != groups[-1]:
                if groups[i] == "P":
                    grouped_table = self.__upd_table[self.__upd_table[self.__applicability_name]==groups[i]]
                    grouped_table = grouped_table[grouped_table["Thrust_Cond"]=="MTO"]
                    grouped_table = grouped_table.drop_duplicates().sort_values(by=self.__segment_no_name)
                    grouped_tables_list.append(grouped_table)

                else:
                    grouped_table = self.__upd_table[self.__upd_table[self.__applicability_name]==groups[i]]
                    grouped_table = grouped_table.drop_duplicates().sort_values(by=self.__segment_no_name)
                    grouped_tables_list.append(grouped_table)
            else:
                for i in range(0, len(groups)-1):
                    indices = grouped_tables_list[i].index.tolist()
                    index_numbers+=indices

                airframe_table = self.__upd_table.drop(index_numbers,axis=0)

                airframe_table = airframe_table.sort_values(by=self.__segment_no_name)
                airframe_table = airframe_table[airframe_table["Applicability"]!="P"].reset_index(drop=True)
                grouped_tables_list.append(airframe_table)

        for i in range(0, len(groups)):
            grouped_tables_list[i]=grouped_tables_list[i].reset_index(drop=True)

        airframe_table = grouped_tables_list[-1]
        airframe_table_drop_indices = []
        for i in range(len(airframe_table["Applicability"])):
            if len(airframe_table["Applicability"][i])==1:
                airframe_table_drop_indices.append(i)
        self.__airframe_table = airframe_table.drop(airframe_table_drop_indices, axis=0)
        self.__airframe_table = self.__airframe_table.reset_index(drop=True)

       
        self.__grouped_tables = grouped_tables_list
        self.__grouped_tables_names = groups
        self.__grouped_std_names = test_csv["Comp_group"].tolist()
        


        
    def __XML_parsing(self, table, table_name,batman_path, std_name, cntrl_xml_file_name):

        string = ".xml"
        mlg_input_files = os.listdir(self.__batman_config)
        file_name = pd.Series(mlg_input_files)[pd.Series(mlg_input_files).str.contains(string,flags=re.IGNORECASE,regex=True)].reset_index(drop=True)[0]
        
        if self.__soldyn_tempFlag == 1:
            self.__soldyn_tempFlag = 0
        
            try:
                self.__tree = ET.parse(self.__batman_config + "/"+ file_name)
                self.__logger.info(f"{self.__batman_config}/{file_name} read successfully.")
            except FileNotFoundError:
                self.__logger.error("XML file not found. Please check the path.")
                raise Exception("XML file not found. Please check the path.")
        
        self.__root = self.__tree.getroot()
        self.__grouping()
        for i in self.__root.iter("params"):
            params = i
        while(len(params)>0):
            params.remove(params[0])
        n = len(table)
        while(len(params)<2*n):
            params.append(ET.Element('param'))
        for i in range(0, int(len(params)/2)):
           
            params[i].attrib = {'id':table['param_code'][i]}
            params[i].text = str(table["param_value"][i])
            params[int(len(params)/2)+i].attrib = {'id':table['param_thrust_code'][i]}
            params[int(len(params)/2)+i].text = str(table["param_thrust_value"][i])
            
            for key, value in params[i].attrib.items():
                params[i].set(key, value.replace('"', "'"))
            for key, value in params[int(len(params)/2)+i].attrib.items():
                params[int(len(params)/2)+i].set(key, value.replace('"', "'"))
                
 
            
            
        j=0 
        while j < int(len(params)/2):
            if float(params[j].text) < 0 and abs(float(params[j].text)) < 1:
                params.remove(params[j])
                j-=1
            j+=1
        
        params.append(ET.Element('param'))
        params[-1].attrib = {'id':'MU_NXP15G_M'}
        params[-1].text = "0.1663"

        xml_path = batman_path+"/"
        string ="batman_"+table_name
        remain_name = ""
        extension = ".csv"
        file_name = self.__filename_issued(xml_path, string, remain_name, extension)
        
        for j in self.__root.iter('steering'):
            j.text = str(file_name)
        for j in self.__root.iter('batman_path'):
            j.text = str(self.__BatmanGroupPath)
        for j in self.__root.iter('simulation_path'):
            j.text = str(self.__SolstatGroupPath)
            
        
        
        with open(self.__params_sumry_filename,"a+") as file:
            lines = file.readlines()
            if len(lines) == 0:
                with open(self.__params_sumry_filename, 'a+') as file:  
                    file.write("\n"+f"{std_name}:" +"\n")
                    file.write(f"{cntrl_xml_file_name}\n")
                    file.write("\n")
                    for i in range(len(params)):  
                        file.write(f"{params[i].attrib.get('id')} = {params[i].text}"+'\n')
            
            else:
                with open(self.__params_sumry_filename, 'a+') as file:
                    
                    if lines[-1].endswith('\n'):
                        file.write("\n\n")
                        file.write(f"{std_name}:" +"\n")
                        file.write(f"{cntrl_xml_file_name}\n")
                        file.write("\n")
                        for i in range(len(params)):
                            file.write(f"{params[i].attrib.get('id')} = {params[i].text}"+'\n')
                    else:
                        file.write("\n\n")
                        file.write('\n'+f"{std_name}:" +"\n")
                        file.write("\n")
                        for i in range(len(params)):
                            file.write(f"{params[i].attrib.get('id')} = {params[i].text}"+'\n')  
                
    def __formatting_xml(self, element):
        rough_string = ET.tostring(element,'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="    ")
    
    def XML(self, table, table_name, batman_path, std_name):
        self.__grouping()
        xml_path = batman_path+"/"
        string ="control_batman_"+table_name
        remain_name = ""
        extension = ".xml"
        file_name = self.__filename_issued(xml_path, string, remain_name, extension)
        self.__control_xml_path = file_name
        self.__XML_parsing(table,table_name,batman_path, std_name, file_name)
        formated_xml = self.__formatting_xml(self.__root)
        formated_xml = '\n'.join([line for line in formated_xml.split('\n') if line.strip()])
        
        
        with open(file_name,"w",encoding="utf-8") as f:
            f.write(formated_xml)
            self.__logger.info(f"{file_name} created successfully.")
            
    def __batman_output(self, table, table_name, batman_path, std_name):
        
        string = ".csv"
        input_files = os.listdir(self.__batman_config)
        file_name = pd.Series(input_files)[pd.Series(input_files).str.contains(string,flags=re.IGNORECASE,regex=True)].reset_index(drop=True)[0]
        
        if self.__batman_tempFlag == 1:
            self.__batman_tempFlag = 0
            try:
                with open(self.__batman_config +"/"+ file_name,'r') as file:
                    self.__df = pd.read_csv(file)
                    self.__logger.info(f"{self.__batman_config}/{file_name} read successfully.")
            except FileNotFoundError:
                self.__logger.error("Batman template not found. Please check the path.")
                raise Exception("Batman template not found. Please check the path.")
            
        self.__df = self.__df.reset_index(drop=True)
        
        self.XML(table, table_name, batman_path, std_name)               
        df = self.__df

        batman_input_list = []
        used_thrust_and_mass_ideal = []
        used_thrust_and_mass = []
        used_thrust_and_mass_roll_out = []
        used_mass_cy = []
        used_mass_flat = []
        pre_flight_equsta_flag = 0
        post_flight_equsta_flag = 0
        #pd.options.mode.copy_on_write = True
        towing_flag = 0
        pushback_flag = 0  


        for i in range(len(table)):

            thrust_value = table["param_thrust_value"][i]
            segment_id = table["Segment_ID"][i]
            mass_value = table["Mass"][i]
            event_id = table["Event_ID"][i]
            d1n_thrust_check = pd.Series(event_id).str.contains("1g",flags=re.IGNORECASE,regex=True)[0] and ~pd.Series(table["Segment_Desc"][i]).str.contains("brak",flags=re.IGNORECASE,regex=True)[0]
            d1n_thrust_check = d1n_thrust_check and float(thrust_value)!=0 and table["Segment_Desc"][i]!="Rotation" 
            d1n_thrust_check = d1n_thrust_check and ~pd.Series(table["Segment_Desc"][i]).str.contains("engine",flags=re.IGNORECASE,regex=True)[0]
            d1n_thrust_check = d1n_thrust_check and ~pd.Series(table["Segment_Desc"][i]).str.contains("take",flags=re.IGNORECASE,regex=True)[0]
            d1n_thrust_check = d1n_thrust_check and ~pd.Series(table["Segment_Desc"][i]).str.contains("dump",flags=re.IGNORECASE,regex=True)[0]


            towing_string = pd.Series(event_id).str.contains("tow",flags=re.IGNORECASE,regex=True)[0]
            pushback_string = pd.Series(event_id).str.contains("push",flags=re.IGNORECASE,regex=True)[0]
            flat_turn_string = pd.Series(event_id).str.contains("ratturn",flags=re.IGNORECASE,regex=True)[0] and pd.Series(table["param_value"][i]).str.contains("0.15",flags=re.IGNORECASE,regex=True)[0] and ~pd.Series(table["Segment_Desc"][i]).str.contains("reverse",flags=re.IGNORECASE,regex=True)[0]

            NL_CY_string = pd.Series(event_id).str.contains("ratturn",flags=re.IGNORECASE,regex=True)[0] and pd.Series(table["param_value"][i]).str.contains("0.3",flags=re.IGNORECASE,regex=True)[0]
            rotation_string = pd.Series(event_id).str.contains("1g",flags=re.IGNORECASE,regex=True)[0] and pd.Series(table["Segment_Desc"][i]).str.contains("rotation",flags=re.IGNORECASE,regex=True)[0]
            engine_run_up_string = pd.Series(event_id).str.contains("engine",flags=re.IGNORECASE,regex=True)[0]

            pre_dump_string = pd.Series(table["Segment_Desc"][i]).str.contains("dump",flags=re.IGNORECASE,regex=True)[0] and pd.Series(table["Segment_Desc"][i]).str.contains("before",flags=re.IGNORECASE,regex=True)[0]
            post_dump_string = pd.Series(table["Segment_Desc"][i]).str.contains("dump",flags=re.IGNORECASE,regex=True)[0] and pd.Series(table["Segment_Desc"][i]).str.contains("after",flags=re.IGNORECASE,regex=True)[0]


            if ((float(table["param_thrust_value"][i])== 0) and (float(table["ENZF"][i])==1) and ([thrust_value, mass_value] not in used_thrust_and_mass)):

                pre_flight_check = pd.Series(table.loc[:,"Phase_Desc"][i]).str.contains("pre",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table.loc[:,"Phase_Desc"][i]).str.contains("take",flags=re.IGNORECASE,regex=True)[0]
                post_flight_check = pd.Series(table.loc[:,"Phase_Desc"][i]).str.contains("post",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table.loc[:,"Phase_Desc"][i]).str.contains("land",flags=re.IGNORECASE,regex=True)[0]
                if pre_flight_check  and pre_flight_equsta_flag == 0:
                    pre_flight_equsta_flag =  1
                    batman_rows = df[pd.Series(df["Masscase Groups"]).str.contains("M_?Fat_?Pre",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[batman_rows["Description"]=="EQUSTA"]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row.loc[:,"Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row.loc[:,"Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                    
                    batman_input_list.append(batman_row)
                    used_thrust_and_mass.append([thrust_value,mass_value])
                elif post_flight_check  and post_flight_equsta_flag == 0:

                    post_flight_equsta_flag = 1
                    batman_rows = df[pd.Series(df.loc[:,"Masscase Groups"]).str.contains("M_?Fat_?Post",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[batman_rows.loc[:,"Description"]=="EQUSTA"]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row.loc[:,"Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row.loc[:,"Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)       
                    batman_input_list.append(batman_row)
                    used_thrust_and_mass.append([thrust_value,mass_value])


            elif (d1n_thrust_check and [thrust_value, mass_value] not in used_thrust_and_mass_ideal) and ~pd.Series(table["Segment_Desc"][i]).str.contains("reverse",flags=re.IGNORECASE,regex=True)[0]:

                pre_flight_check = pd.Series(table["Phase_Desc"][i]).str.contains("pre",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table["Phase_Desc"][i]).str.contains("take",flags=re.IGNORECASE,regex=True)[0]
                post_flight_check = pd.Series(table["Phase_Desc"][i]).str.contains("post",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table["Phase_Desc"][i]).str.contains("land",flags=re.IGNORECASE,regex=True)[0]
                if(pre_flight_check):
                    batman_rows = df[pd.Series(df["Masscase Groups"]).str.contains("M_?Fat_?Pre",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[pd.Series(batman_rows["Maneuvers"]).str.contains("thrust",flags=re.IGNORECASE,regex=True)].reset_index(drop=True) 
                    batman_row = batman_row[pd.Series(batman_row["Maneuvers"]).str.contains("ideal",flags=re.IGNORECASE,regex=True)]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row.loc[:,"Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row.loc[:,"Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                    maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"\{(\w+)\}",'{'+table["param_thrust_code"][i]+'}',regex=True)
                    maneuver_string = maneuver_string.str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                    batman_row.loc[:,'Maneuvers'] = maneuver_string 
                    batman_input_list.append(batman_row)
                    used_thrust_and_mass_ideal.append([thrust_value,mass_value])
                    used_thrust_and_mass.append([thrust_value,mass_value])

                elif(post_flight_check):

                    batman_rows = df[pd.Series(df["Masscase Groups"]).str.contains("M_?Fat_?Post",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[pd.Series(batman_rows["Maneuvers"]).str.contains("thrust",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_row[pd.Series(batman_row["Description"]).str.contains("ideal",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_row[pd.Series(batman_row["Maneuvers"]).str.contains("d1n",flags=re.IGNORECASE,regex=True)]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row.loc[:,"Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row.loc[:,"Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                    maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"\{(\w+)\}",'{'+ table["param_thrust_code"][i]+'}',regex=True)
                    maneuver_string = maneuver_string.str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                    batman_row.loc[:,'Maneuvers'] = maneuver_string 

                    batman_input_list.append(batman_row)
                    used_thrust_and_mass_ideal.append([thrust_value,mass_value])
                    used_thrust_and_mass.append([thrust_value,mass_value])

            elif (d1n_thrust_check and [thrust_value, mass_value] not in used_thrust_and_mass_roll_out and  pd.Series(table["Segment_Desc"][i]).str.contains("reverse",flags=re.IGNORECASE,regex=True)[0]):
                pre_flight_check = pd.Series(table["Phase_Desc"][i]).str.contains("pre",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table["Phase_Desc"][i]).str.contains("take",flags=re.IGNORECASE,regex=True)[0]
                post_flight_check = pd.Series(table["Phase_Desc"][i]).str.contains("post",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table["Phase_Desc"][i]).str.contains("land",flags=re.IGNORECASE,regex=True)[0]
                if(pre_flight_check):

                    batman_rows = df[pd.Series(df["Masscase Groups"]).str.contains("M_?Fat_?Pre",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[pd.Series(batman_rows["Maneuvers"]).str.contains("thrust",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)

                    batman_row = batman_row[pd.Series(batman_row["Description"]).str.contains("reverse",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)

                    batman_row = batman_row[pd.Series(batman_row["Maneuvers"]).str.contains("d1n",flags=re.IGNORECASE,regex=True)]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row.loc[:,"Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                    maneuver_string = pd.Series(batman_row.loc[:,"Maneuvers"]).str.replace(r"\{(\w+)\}",'{'+table["param_thrust_code"][i]+'}',regex=True)
                    maneuver_string = maneuver_string.str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                    
                    batman_row.loc[:,'Maneuvers'] = maneuver_string 
                    batman_input_list.append(batman_row)
                    used_thrust_and_mass_roll_out.append([thrust_value,mass_value])
                    used_thrust_and_mass.append([thrust_value,mass_value])

                elif(post_flight_check):

                    batman_rows = df[pd.Series(df["Masscase Groups"]).str.contains("M_?Fat_?Post",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[pd.Series(batman_rows["Maneuvers"]).str.contains("thrust",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_row[pd.Series(batman_row["Description"]).str.contains("reverse",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_row[pd.Series(batman_row["Maneuvers"]).str.contains("d1n",flags=re.IGNORECASE,regex=True)]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                    maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"\{(\w+)\}",'{'+table["param_thrust_code"][i]+'}',regex=True)
                    maneuver_string = maneuver_string.str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                    batman_row.loc[:,'Maneuvers'] = maneuver_string 

                    batman_input_list.append(batman_row)
                    used_thrust_and_mass_roll_out.append([thrust_value,mass_value])
                    used_thrust_and_mass.append([thrust_value,mass_value])

            elif towing_string and towing_flag==0:
                towing_flag=1
                batman_row = df[pd.Series(df["Description"]).str.contains("tow",flags=re.IGNORECASE,regex=True)]
                batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"\{(\w+)\}",'{'+table["param_code"][i]+'}',regex=True)
                batman_row.loc[:,'Maneuvers'] = maneuver_string 
                batman_input_list.append(batman_row)

            elif (pushback_string and pushback_flag==0):
                pushback_flag=1
                batman_row = df[pd.Series(df["Description"]).str.contains("push",flags=re.IGNORECASE,regex=True)]
                batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"\{(\w+)\}",'{'+table["param_code"][i]+'}',regex=True)
                batman_row.loc[:,'Maneuvers'] = maneuver_string 
                batman_input_list.append(batman_row)

            elif flat_turn_string and mass_value not in used_mass_flat:

                pre_flight_check = pd.Series(table["Phase_Desc"][i]).str.contains("pre",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table["Phase_Desc"][i]).str.contains("take",flags=re.IGNORECASE,regex=True)[0]
                post_flight_check = pd.Series(table["Phase_Desc"][i]).str.contains("post",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table["Phase_Desc"][i]).str.contains("land",flags=re.IGNORECASE,regex=True)[0]
                if pre_flight_check:
                    batman_rows = df[pd.Series(df["Masscase Groups"]).str.contains("M_?Fat_?Pre",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[pd.Series(batman_rows["Description"]).str.contains("flat",flags=re.IGNORECASE,regex=True)]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                    maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                    maneuver_string = pd.Series(maneuver_string).str.replace(r"=-(\d+.?\d*)",'=-' + '${'+str(table["param_code"][i])+'}',regex=True)
                    batman_row.loc[:,'Maneuvers'] = maneuver_string 
                    batman_input_list.append(batman_row)
                    used_mass_flat.append(mass_value)  
                elif post_flight_check:   

                    batman_rows = df[pd.Series(df["Masscase Groups"]).str.contains("M_?Fat_?Post",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[pd.Series(batman_rows["Description"]).str.contains("flat",flags=re.IGNORECASE,regex=True)]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                    maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                    maneuver_string = pd.Series(maneuver_string).str.replace(r"=-(\d+.?\d*)",'=-' + '${'+str(table["param_code"][i])+'}',regex=True)
                    
                    batman_row.loc[:,'Maneuvers'] = maneuver_string 
                    batman_input_list.append(batman_row)
                    used_mass_flat.append(mass_value)

            elif NL_CY_string and mass_value not in used_mass_cy:
                pre_flight_check = pd.Series(table["Phase_Desc"][i]).str.contains("pre",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table["Phase_Desc"][i]).str.contains("take",flags=re.IGNORECASE,regex=True)[0]
                post_flight_check = pd.Series(table["Phase_Desc"][i]).str.contains("post",flags=re.IGNORECASE,regex=True)[0] or pd.Series(table["Phase_Desc"][i]).str.contains("land",flags=re.IGNORECASE,regex=True)[0]

                if pre_flight_check:
                    batman_rows = df[pd.Series(df["Masscase Groups"]).str.contains("M_?Fat_?Pre",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[pd.Series(batman_rows["Description"]).str.contains("Cy",flags=re.IGNORECASE,regex=True)]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                    maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                    maneuver_string = pd.Series(maneuver_string).str.replace(r"=-(\d+.?\d*)",'=-' + '${'+str(table["param_code"][i])+'}',regex=True)
                    batman_row.loc[:,'Maneuvers'] = maneuver_string 
                    batman_input_list.append(batman_row)
                    used_mass_cy.append(mass_value)

                elif post_flight_check:
                    batman_rows = df[pd.Series(df["Masscase Groups"]).str.contains("M_?Fat_?Post",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
                    batman_row = batman_rows[pd.Series(batman_rows["Description"]).str.contains("Cy",flags=re.IGNORECASE,regex=True)]
                    batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                    batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                    maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                    maneuver_string = pd.Series(maneuver_string).str.replace(r"=-(\d+.?\d*)",'=-' + '${'+str(table["param_code"][i])+'}',regex=True)
                    batman_row.loc[:,'Maneuvers'] = maneuver_string 
                    batman_input_list.append(batman_row)
                    used_mass_cy.append(mass_value)


            elif engine_run_up_string:
                batman_row = df[pd.Series(df["Description"]).str.contains("engine",flags=re.IGNORECASE,regex=True)]
                batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"\{(\w+)\}",'{'+table["param_thrust_code"][i]+'}',regex=True)
                maneuver_string = maneuver_string.str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                batman_row.loc[:,'Maneuvers'] = maneuver_string  
                batman_input_list.append(batman_row)


            elif rotation_string:
                batman_row = df[pd.Series(df["Description"]).str.contains("rotation",flags=re.IGNORECASE,regex=True)]
                batman_row = batman_row[~pd.Series(batman_row["Description"]).str.contains("increme",flags=re.IGNORECASE,regex=True)]
                batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                
                batman_row.loc[:,'Maneuvers'] = maneuver_string 

                batman_input_list.append(batman_row)

            elif pre_dump_string:
                batman_row = df[pd.Series(df["Description"]).str.contains("dump",flags=re.IGNORECASE,regex=True)]
                batman_row = batman_row[pd.Series(batman_row["Description"]).str.contains("pre",flags=re.IGNORECASE,regex=True)]
                batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                batman_row.loc[:,'Maneuvers'] = maneuver_string 
                batman_input_list.append(batman_row)

            elif post_dump_string:

                batman_row = df[pd.Series(df["Description"]).str.contains("dump",flags=re.IGNORECASE,regex=True)]
                batman_row = batman_row[pd.Series(batman_row["Description"]).str.contains("post",flags=re.IGNORECASE,regex=True)]
                batman_row.loc[:,'Filename'] = pd.Series(batman_row["Filename"]).str.replace(r"(\d+)",segment_id,regex=True)
                batman_row.loc[:,'Additional Lines'] =  pd.Series(batman_row["Additional Lines"]).str.replace(r"(\d+)",segment_id,regex=True)
                maneuver_string = pd.Series(batman_row["Maneuvers"]).str.replace(r"=(\d+.?\d*)",'=' + '${'+str(table["param_code"][i])+'}',regex=True)
                batman_row.loc[:,'Maneuvers'] = maneuver_string
                batman_input_list.append(batman_row)
            
        if len(batman_input_list)==0:
            self.__logger.warning(f"{std_name} for Batman is empty")
            print(f"{std_name} for Batman is empty")
        
        if len(batman_input_list)>0:
            batman_input = batman_input_list[0]
            for x in batman_input_list:
                batman_input = batman_input.append(x)
            batman_input = batman_input.drop_duplicates().reset_index(drop=True)
            return batman_input 
        return pd.DataFrame()
    
    def __Batman_shell_scripting(self):
        input_files = os.listdir(self.__batman_config)
        shell_filename = pd.Series(input_files)[pd.Series(input_files).str.contains("cmd_line.sh",flags=re.IGNORECASE,regex=True)].tolist()[0]
        with open(f"{self.__batman_config}/{shell_filename}", "r") as file:
            shell_file = file.read()
        old = re.findall(r'\$control_xml_path', shell_file, re.DOTALL)[0]
        
        new = ' '+self.__control_xml_path
        shell_file = re.sub(re.escape(old),new,shell_file)
        path = os.path.normpath(self.__control_xml_path)
        components = path.split(os.sep)
        new_output_path_1 = os.sep.join(components[:-1])+"/"
        
        shell_filename_issue = self.__filename_issued(new_output_path_1, shell_filename[:-3]+"_", "", ".sh") 
        self.__batman_exec_path_list.append(shell_filename_issue)
        with open(shell_filename_issue, "w") as file:
            file.write(shell_file)
        

    def batman(self):
        self.__grouping()
        path = self.__output_dir 
        try:
            os.path.exists(path)
        except:
            self.__logger.error("Please check the output_dir path.")
            raise Exception("Please check the output_dir path.")
            
        if self.__batman_smry_tempFlag == 0:
            self.__batman_smry_tempFlag = 1
            self.__soldyn_sumry("Updated parameters in batman control XML files: \n")
         
        for i in range(len(self.__grouped_tables_names)):
            GroupExist = os.path.exists(path+"/"+ self.__grouped_std_names[i])
            if not GroupExist:
                os.makedirs(path+"/"+ self.__grouped_std_names[i])
            self.__BatmanGroupPath = path+"/"+ self.__grouped_std_names[i]
            
            BatmanGroupExist = os.path.exists(path+"/"+ self.__grouped_std_names[i]+"/BATMAN")
            if not BatmanGroupExist:
                os.makedirs(path+"/"+ self.__grouped_std_names[i]+"/BATMAN")
            self.__BatmanGroupPath = path+"/"+ self.__grouped_std_names[i]+"/BATMAN"
            
            BatmanInputExist = os.path.exists(path+"/"+ self.__grouped_std_names[i]+"/BATMAN"+"/Inputs")
            if not BatmanInputExist:
                os.makedirs(path+"/"+ self.__grouped_std_names[i]+"/BATMAN"+"/Inputs")
            self.__BatmanInputPath = path+"/"+ self.__grouped_std_names[i]+"/BATMAN"+"/Inputs"
            BatmanOutputExist = os.path.exists(path+"/"+ self.__grouped_std_names[i]+"/BATMAN"+"/Outputs")
            if not BatmanOutputExist:
                os.makedirs(path+"/"+ self.__grouped_std_names[i]+"/BATMAN"+"/Outputs")
            self.__BatmanOutputPath = path+"/"+ self.__grouped_std_names[i]+"/BATMAN"+"/Outputs"
            
            SolstatGroupExist = os.path.exists(path+"/"+ self.__grouped_std_names[i]+"/SOLSTAT")
            if not SolstatGroupExist:
                os.makedirs(path+"/"+ self.__grouped_std_names[i]+"/SOLSTAT")
            self.__SolstatGroupPath = path+"/"+ self.__grouped_std_names[i]+"/SOLSTAT"
            self.__logger.info(f"Batman setup for {self.__grouped_std_names[i]} group started.")
            print(f"Batman setup for {self.__grouped_std_names[i]} group started.")
            table = self.__grouped_tables[i]
            table = table[table["Event_ID"]!="Bumps"]
            table = table[table["Event_ID"]!="DynLand"]
           # table = table[table["Segment_Desc"]!="Rotation"]
           # table = table[~table["Segment_Desc"].str.contains("lift dumping",flags=re.IGNORECASE,regex=True)]
            table = table[~table["Event_ID"].str.contains("gust",flags=re.IGNORECASE,regex=True)]
            table = table.reset_index(drop=True)
            table_name = self.__grouped_tables_names[i]
            std_name = self.__grouped_std_names[i]
            batman_table = self.__batman_output(table,table_name,self.__BatmanInputPath,std_name)
            
            batman_path_ = self.__BatmanInputPath+"/"
            string ="batman_"+table_name
            remain_name = ""
            extension = ".csv"
            file_name = self.__filename_issued(batman_path_, string, remain_name, extension)
            self.__batman_file_name=file_name
  
            
            with open(file_name,"w") as f:
                batman_table.to_csv(f,index=False)
                self.__Batman_shell_scripting()
                self.__logger.info(f"{file_name} is created successfully.")
                self.__logger.info(f"Batman setup for {self.__grouped_std_names[i]} group completed.")
                print(f"Batman setup for {self.__grouped_std_names[i]} group completed.")

    def soldyn_setup(self,table, soldyn_input_path,grouping_name, std_name):
        path = self.__output_dir 
        try:
            os.path.exists(path)
        except:
            self.__logger.error("Please check the output_dir path.")
            raise Exception("Please check the output_dir path.")
            
        if self.__soldyn_smry_tempFlag == 0:
            self.__soldyn_smry_tempFlag = 1
            self.__soldyn_sumry("\n\nUpdated parameters in Soldyn XML files: \n")

        self.__soldyn_mlg(table, soldyn_input_path,grouping_name, std_name)
        
        if not (grouping_name =="SF" and self.__SFBumpsFlag==0):
            self.__soldyn_bumps(table, soldyn_input_path,grouping_name, std_name)
        
        if grouping_name !="SF":
            self.__soldyn_bumps_1g(table, soldyn_input_path,grouping_name, std_name)
        else:
            table = table.sort_values(by="HLD_Config").reset_index(drop=True)
            SF_grouped = table.groupby("HLD_Config") 
            SF_sub = [group for _, group  in SF_grouped]
            for i in range(len(SF_sub)):
                self.__soldyn_bumps_1g(SF_sub[i], soldyn_input_path,grouping_name, std_name)
        
    def __closing_tags(self, elem):
        if elem.text is None:
            elem.text = ""
        for subelem in elem:
            self.__closing_tags(subelem)
        
        
    def __filename_issued(self, path, string, remain_name, extension):
        if not os.path.exists(f"{path}{string}1{remain_name}{extension}"):
            return f"{path}{string}1{remain_name}{extension}"
        i=1
        while os.path.exists(f"{path}{string}{i}{remain_name}{extension}"):
            i+=1
        return f"{path}{string}{i}{remain_name}{extension}"
    
    def __shell_scripting(self, row_case, input_files, output_filename):
        for j in row_case.iter('aerodynamic'):
            aerodynamic_Flag = j.text
            break
        
        if aerodynamic_Flag == "true":
            shell_filename = pd.Series(input_files)[pd.Series(input_files).str.contains("FIL.sh",flags=re.IGNORECASE,regex=True)].tolist()[0]
            with open(f"{self.__soldyn_config}/{shell_filename}", "r") as file:
                shell_file = file.read()
            old_CC = re.findall(r'CC="([^"]*)"', shell_file, re.DOTALL)[0]
            old_output_path = re.findall(r'OUTPUT_PATH="([^"]*)"', shell_file, re.DOTALL)[0]
            new_CC = output_filename
            path = os.path.normpath(output_filename)
            components = path.split(os.sep)
            new_output_path_1 = os.sep.join(components[:-1])+"/"
            components[-3] = 'Outputs'
            new_output_path = os.sep.join(components[:-1])+"/"
            modified_shell_file = re.sub(re.escape(old_CC),new_CC,shell_file)
            modified_shell_file = re.sub(re.escape(old_output_path),new_output_path,modified_shell_file)
            
            shell_filename_issue = self.__filename_issued(new_output_path_1, shell_filename[:-3]+"_", "", ".sh")
            
            self.__soldyn_exec_path_list.append(shell_filename_issue)
            with open(shell_filename_issue, "w") as file:
                file.write(modified_shell_file)
                
        else:
            shell_filenames = pd.Series(input_files)[pd.Series(input_files).str.contains(".sh",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
            shell_filename = shell_filenames[~shell_filenames.str.contains("FIL",flags=re.IGNORECASE,regex=True)].to_list()[0]
            with open(f"{self.__soldyn_config}/{shell_filename}", "r") as file:
                shell_file = file.read()
            old_CC = re.findall(r'CC="([^"]*)"', shell_file, re.DOTALL)[0]
            old_output_path = re.findall(r'OUTPUT_PATH="([^"]*)"', shell_file, re.DOTALL)[0]
            new_CC = output_filename
            path = os.path.normpath(output_filename)
            components = path.split(os.sep)
            new_output_path_1 = os.sep.join(components[:-1])+"/"
            components[-3] = 'Output'
            new_output_path = os.sep.join(components[:-1])+"/"
            modified_shell_file = re.sub(re.escape(old_CC),new_CC,shell_file)
            modified_shell_file = re.sub(re.escape(old_output_path),new_output_path,modified_shell_file)
            
            shell_filename_issue = self.__filename_issued(new_output_path_1, shell_filename[:-3]+"_", "", ".sh") 
            
            self.__soldyn_exec_path_list.append(shell_filename_issue)
            
            with open(shell_filename_issue, "w") as file:
                file.write(modified_shell_file)
                
    def __soldyn_sumry(self, text):
        with open(self.__params_sumry_filename,"a+") as file:
            lines = file.readlines()
        if len(lines) == 0:
            with open(self.__params_sumry_filename, 'a+') as file:
                file.write(f"{text}")
        else:
            with open(self.__params_sumry_filename, 'a+') as file:
                if lines[-1].endswith('\n'):
                    file.write(f"{text}")
                else:
                    file.write(f"{text}")
 

    def __soldyn_mlg(self,table,soldyn_input_path,grouping_name, std_name):
        MLG_segment = table[table["Segment_Desc"].str.contains("MLG",flags=re.IGNORECASE, regex=True)]
        MLG_segment = MLG_segment[~MLG_segment["Event_ID"].str.contains("1g",flags=re.IGNORECASE, regex=True)].reset_index(drop=True)

        if len(MLG_segment)!=0:
            string = "FLx"
            mlg_input_files = os.listdir(self.__soldyn_config)

            file_names = pd.Series(mlg_input_files)[pd.Series([i[0:3]==string for i in mlg_input_files])]
            if len(file_names)!=0:
                file_names = file_names.reset_index(drop=True)
                file_name = file_names[0]
                col1 = [i/2 for i in range(2,19)]
                col2 = [chr(i) for i in range(91-17,91)]
                col2 = ["FL"+i for i in col2]
                mnemonic_codes = pd.DataFrame(col1) 
                mnemonic_codes.rename(columns={0:"VSink"},inplace=True)
                mnemonic_codes["mnemonic_code"] = col2
                tree = ET.parse(self.__soldyn_config+"/"+file_name)
                mlg_touch_smryFlag = 0
                
                
                if self.__mlg_touch_temp_Flag == 1:
                    self.__mlg_touch_temp_Flag = 0
                    self.__logger.info(f"{self.__soldyn_config}/{file_name} read successfully.")
                root = tree.getroot()
                case = root.find('Calculation_Case')
                no_cases = len(root.findall('Calculation_Case'))
        
                while(no_cases>0):
                    root.remove(root.find('Calculation_Case'))
                    no_cases = len(root.findall('Calculation_Case'))
                
                remain_name = str(MLG_segment["Mission_ID"][0][0])+str(MLG_segment["Segment_ID"][0])

                temp_dir = self.__filename_issued(soldyn_input_path+"/", string, remain_name, "")
                directoryExists = os.path.exists(temp_dir)
                if not directoryExists:
                    os.makedirs(temp_dir)
                path = temp_dir+"/"
                output_file_name = path+os.path.basename(temp_dir)+".xml"
                
                for i in range(len(MLG_segment)):
        
                    row_case = copy.deepcopy(case)
                    vsink = MLG_segment["param_value"][i]
                    codes_row = pd.Series(mnemonic_codes[pd.to_numeric(mnemonic_codes["VSink"])==float(vsink)]["mnemonic_code"]).reset_index(drop=True)[0]
    
                    for j in row_case.iter('maneuver_mnemonic'):
                        j.text = codes_row
                    for j in row_case.iter('maneuver_name'):
                        j.text = str(vsink)+'ft/s dynamic landing'
                    for j in row_case.iter('mass_case_name'):
                        j.text = MLG_segment["Mass_Case"][i] +'Z'
                    for j in row_case.iter('horizontal_speed'):
                        j.text = str(MLG_segment["VCAS"][i])
                    for j in row_case.iter('vertical_speed'):
                        j.text = str(vsink)
        
                    root.append(row_case)
                    
                    name = string+str(MLG_segment["Mission_ID"][0][0])+str(MLG_segment["Segment_ID"][0])
                    
                    if mlg_touch_smryFlag == 0:
                        mlg_touch_smryFlag = 1
                        self.__soldyn_sumry("\n"+f"{std_name} - {name}" +"\n")
                        self.__soldyn_sumry(f"{output_file_name}\n\n")
                    self.__soldyn_sumry(f"Case {i+1}:\n")
                    self.__soldyn_sumry(f"maneuver_mnemonic = {codes_row}\n")
                    self.__soldyn_sumry(f"maneuver_name = {vsink} ft/s dynamic landing\n")
                    self.__soldyn_sumry(f"mass_case_name = {MLG_segment['Mass_Case'][i]}Z\n")
                    self.__soldyn_sumry(f"horizontal_speed = {MLG_segment['VCAS'][i]}\n")
                    self.__soldyn_sumry(f"vertical_speed = {vsink}\n\n")

        
                root.find('Number_of_Cases').text = str(len(root.findall('Calculation_Case')))
        
                et_str = ET.tostring(root, encoding='utf-8', method='xml')
                root = etree.fromstring(et_str)
                self.__closing_tags(root)
                
                MLG_segment = MLG_segment.reset_index(drop=True)

                with open(output_file_name,'wb') as f:
                    f.write(etree.tostring(root, pretty_print=True))
                    self.__logger.info(f"{output_file_name} created successfully.")      
                self.__shell_scripting(row_case, mlg_input_files, output_file_name)    

        else:
            self.__logger.warning(f"MLG touchdown for {std_name} group is empty.")
            print(f"MLG touchdown for {std_name} group is empty.")


    def __soldyn_bumps(self,table,soldyn_input_path,grouping_name, std_name):
        bumps_segment = table[table["Event_ID"]=="Bumps"].reset_index(drop=True)
        
        if len(bumps_segment)!=0:
            bumps_input_path = self.__soldyn_config
            bumps_input_files = os.listdir(bumps_input_path)
            
            if self.__aircraft_type=="A318":
                wheelbase = 33.6  # feets
            elif self.__aircraft_type=="A319":
                wheelbase = 36.2  # feets
            elif self.__aircraft_type=="A320":
                wheelbase = 41.5  # feets
            elif self.__aircraft_type=="A321":
                wheelbase = 55.5  # feets
    
            bump_lengths = [20, 30, 1*wheelbase, 60, 2*wheelbase, 120, 160] # feets
            bump_lengths = [i*0.3048 for i in bump_lengths] # meters
            
            
    
            for i in range(len(bumps_segment)):
                taxi_check = pd.Series(bumps_segment["Segment_Desc"][i]).str.contains("taxi",flags=re.IGNORECASE,regex=True)[0]
                if taxi_check:
                    string = "FHT"
                   
                    file_names = pd.Series(bumps_input_files)[pd.Series([i[0:3]==string for i in bumps_input_files])]
                    bumps_FHT_sumry_flag = 0
                    
                    if len(file_names)!=0:
                        file_names = file_names.reset_index(drop=True)
                        file_name = file_names[0]
                        tree = ET.parse(bumps_input_path+"/"+file_name)
                        if self.__bumps_temp_FHT_Flag == 1:
                            self.__bumps_temp_FHT_Flag = 0
                            self.__logger.info(f"{bumps_input_path}/{file_name} read successfully.")

                        root = tree.getroot()
                        cntr=0
                        
                        remain_name = str(bumps_segment["Mission_ID"][i][0])+str(bumps_segment["Segment_ID"][i])
                        temp_dir = self.__filename_issued(soldyn_input_path+"/", string, remain_name, "")
                        directoryExists = os.path.exists(temp_dir)
                        if not directoryExists:
                            os.makedirs(temp_dir)
                        path = temp_dir+"/"
                        output_file_name = path+os.path.basename(temp_dir)+".xml"
                        
                        for case in root.iter('Calculation_Case'):
                            for j in case.iter('mass_case_name'):
                                j.text = bumps_segment["Mass_Case"][i]+'Z'
                            for j in case.iter('horizontal_speed'):
                                j.text = str(bumps_segment["VCAS"][i])
                            for j in case.iter('maneuver_number'):
                                j.text = '11'+str(cntr+1)
                            for j in case.iter('bump_length'):
                                j.text = str(bump_lengths[cntr])
                            cntr += 1
                            
                            name = string+str(bumps_segment["Mission_ID"][i][0])+str(bumps_segment["Segment_ID"][i])
                            if bumps_FHT_sumry_flag == 0:
                                bumps_FHT_sumry_flag = 1
                                self.__soldyn_sumry("\n"+f"{std_name} - {name}" +"\n")
                                self.__soldyn_sumry(f"{output_file_name}\n\n")
                            self.__soldyn_sumry(f"Case {cntr}:\n")
                            self.__soldyn_sumry(f"maneuver_number = 11{cntr}\n")
                           
                            self.__soldyn_sumry(f"mass_case_name = {bumps_segment['Mass_Case'][i]}\n")
                            self.__soldyn_sumry(f"horizontal_speed = {bumps_segment['VCAS'][i]}\n")
                            self.__soldyn_sumry(f"bump_length = {bump_lengths[cntr-1]}\n\n")
                            
                        et_str = ET.tostring(root, encoding='utf-8', method='xml')
                        root = etree.fromstring(et_str)
                        self.__closing_tags(root)

        
                        with open(output_file_name,'wb') as f:
                            f.write(etree.tostring(root, pretty_print=True))
                            self.__logger.info(f"{output_file_name} created successfully.")      
                        self.__shell_scripting(root, bumps_input_files, output_file_name)
    
    
                take_off_run_check = pd.Series(bumps_segment["Segment_Desc"][i]).str.contains("take",flags=re.IGNORECASE,regex=True)[0]
                if take_off_run_check:
                    string = "FHR"
                    bumps_FHR_sumry_flag = 0
                    file_names = pd.Series(bumps_input_files)[pd.Series([i[0:3]==string for i in bumps_input_files])]
                    if len(file_names)!=0:
                        file_names = file_names.reset_index(drop=True)
                        file_name = file_names[0]
                        tree = ET.parse(bumps_input_path+"/"+file_name)
                        if self.__bumps_temp_FHR_Flag == 1:
                            self.__bumps_temp_FHR_Flag = 0
                            self.__logger.info(f"{bumps_input_path}/{file_name} read successfully.")
                        
                        root = tree.getroot()
                        cntr=0
                        remain_name = str(bumps_segment["Mission_ID"][i][0])+str(bumps_segment["Segment_ID"][i])
                       
                        temp_dir = self.__filename_issued(soldyn_input_path+"/", string, remain_name, "")
                        directoryExists = os.path.exists(temp_dir)
                        if not directoryExists:
                            os.makedirs(temp_dir)
                        path = temp_dir+"/"
                        output_file_name = path+os.path.basename(temp_dir)+".xml"
                        
                        for case in root.iter('Calculation_Case'):
                            for j in case.iter('mass_case_name'):
                                j.text = bumps_segment["Mass_Case"][i]+'Z'
                            for j in case.iter('horizontal_speed'):
                                j.text = str(bumps_segment["VCAS"][i])
                            for j in case.iter('maneuver_number'):
                                j.text = '11'+str(cntr+1)
                            for j in case.iter('bump_length'):
                                j.text = str(bump_lengths[cntr])
                            for j in case.iter('aerodynamic'):
                                j.text = "true"
                            for j in case.iter('thrust'):
                                j.text = str(float(bumps_segment["param_thrust_value"][i])*10)
                            cntr += 1
                            
                            name = string+str(bumps_segment["Mission_ID"][i][0])+str(bumps_segment["Segment_ID"][i])
                            if bumps_FHR_sumry_flag == 0:
                                bumps_FHR_sumry_flag = 1
                                self.__soldyn_sumry("\n"+f"{std_name} - {name}" +"\n")
                                self.__soldyn_sumry(f"{output_file_name}\n\n")
                            self.__soldyn_sumry(f"Case {cntr}:\n")
                            self.__soldyn_sumry(f"maneuver_number = 11{cntr}\n")
                            
                            self.__soldyn_sumry(f"mass_case_name = {bumps_segment['Mass_Case'][i]}\n")

                            self.__soldyn_sumry(f"horizontal_speed = {bumps_segment['VCAS'][i]}\n")
                            self.__soldyn_sumry(f"bump_length = {bump_lengths[cntr-1]}\n")
                            self.__soldyn_sumry("aerodynamic = true\n")
                            self.__soldyn_sumry(f"thrust = {float(bumps_segment['param_thrust_value'][i])}\n\n")

                        et_str = ET.tostring(root, encoding='utf-8', method='xml')
                        root = etree.fromstring(et_str)
                        self.__closing_tags(root)
        

                        with open(output_file_name,'wb') as f:
                            f.write(etree.tostring(root, pretty_print=True))
                            self.__logger.info(f"{output_file_name} created successfully.")
                        self.__shell_scripting(root, bumps_input_files, output_file_name)
    
 
                roll_out_check = pd.Series(bumps_segment["Segment_Desc"][i]).str.contains("roll",flags=re.IGNORECASE,regex=True)[0]
                if roll_out_check:
                    string = "FLR"
                    bumps_FLR_sumry_flag = 0
                    file_names = pd.Series(bumps_input_files)[pd.Series([i[0:3]==string for i in bumps_input_files])]
                    if len(file_names)!=0:
                        file_names = file_names.reset_index(drop=True)
                        file_name = file_names[0]   
                        tree = ET.parse(bumps_input_path+"/"+file_name)
                        if self.__bumps_temp_FLR_Flag == 1:
                            self.__bumps_temp_FLR_Flag = 0
                            self.__logger.info(f"{bumps_input_path}/{file_name} read successfully.")
                        
                        root = tree.getroot()
                        cntr=0
                        remain_name = str(bumps_segment["Mission_ID"][i][0])+str(bumps_segment["Segment_ID"][i])
                        temp_dir = self.__filename_issued(soldyn_input_path+"/", string, remain_name, "")
                        directoryExists = os.path.exists(temp_dir)
                        if not directoryExists:
                            os.makedirs(temp_dir)
                        path = temp_dir+"/"
                        output_file_name = path+os.path.basename(temp_dir)+".xml"                        
                        for case in root.iter('Calculation_Case'):
                            for j in case.iter('mass_case_name'):
                                j.text = bumps_segment["Mass_Case"][i]+'Z'
                            for j in case.iter('horizontal_speed'):
                                j.text = str(bumps_segment["VCAS"][i])
                            for j in case.iter('maneuver_number'):
                                j.text = '11'+str(cntr+1)
                            for j in case.iter('bump_length'):
                                j.text = str(bump_lengths[cntr])
                            cntr += 1
                            
                            name = string+str(bumps_segment["Mission_ID"][i][0])+str(bumps_segment["Segment_ID"][i])
                            if bumps_FLR_sumry_flag == 0:
                                bumps_FLR_sumry_flag = 1
                                self.__soldyn_sumry("\n"+f"{std_name} - {name}" +"\n")
                                self.__soldyn_sumry(f"{output_file_name}\n\n")
                            self.__soldyn_sumry(f"Case {cntr}:\n")
                            self.__soldyn_sumry(f"maneuver_number = 11{cntr}\n")
                            
                            self.__soldyn_sumry(f"mass_case_name = {bumps_segment['Mass_Case'][i]}\n")

                            self.__soldyn_sumry(f"horizontal_speed = {bumps_segment['VCAS'][i]}\n")
                            self.__soldyn_sumry(f"bump_length = {bump_lengths[cntr-1]}\n")

        
                        et_str = ET.tostring(root, encoding='utf-8', method='xml')
                        root = etree.fromstring(et_str)
                        self.__closing_tags(root)
        

        
                        with open(output_file_name,'wb') as f:
                            f.write(etree.tostring(root, pretty_print=True))
                            self.__logger.info(f"{output_file_name} created successfully.")
                        self.__shell_scripting(root, bumps_input_files, output_file_name)
                        
        else:
            self.__logger.warning(f"Bumps for {std_name} group is empty.")
            print(f"Bumps for {std_name} group is empty.")

    def __soldyn_bumps_1g(self,table,soldyn_input_path,grouping_name, std_name):
        bumps_1g_segment = table[table["Segment_Desc"].str.contains("take",flags=re.IGNORECASE,regex=True)]
        bumps_1g_segment = bumps_1g_segment[bumps_1g_segment["Event_ID"].str.contains("1g",flags=re.IGNORECASE,regex=True)].reset_index(drop=True)
        if len(bumps_1g_segment)!=0:
            string = "FZ1"
            bumps_1g_input_files = os.listdir(self.__soldyn_config)
            
            file_names = pd.Series(bumps_1g_input_files)[pd.Series([i[0:3]==string for i in bumps_1g_input_files])]
           
            
            if len(file_names)!=0:
                file_names = file_names.reset_index(drop=True)
                file_name = file_names[0]
                bumps_FZ1_sumry_flag = 0
                tree = ET.parse(self.__soldyn_config+"/"+file_name)
                if self.__bumps_1g_temp_Flag == 1:
                    self.__bumps_1g_temp_Flag = 0
                    self.__logger.info(f"{self.__soldyn_config}/{file_name} read successfully")
                
                root = tree.getroot()
                case = root.find('Calculation_Case')
                no_cases = len(root.findall('Calculation_Case'))
        
                while(no_cases>0):
                    root.remove(root.find('Calculation_Case'))
                    no_cases = len(root.findall('Calculation_Case'))
        
                cntr=0
                string = "FZ1"+str(bumps_1g_segment["Segment_ID"][0][0])+str(bumps_1g_segment["Mission_ID"][0][0])+'xx_'
        
    
                temp_dir = self.__filename_issued(soldyn_input_path+"/", string, "", "")
                directoryExists = os.path.exists(temp_dir)
                if not directoryExists:
                    os.makedirs(temp_dir)
                path = temp_dir+"/"
                output_file_name = path+os.path.basename(temp_dir)+".xml"
                for i in range(len(bumps_1g_segment)):
        
                    row_case = copy.deepcopy(case)
        
                    for j in row_case.iter('maneuver_name'):
                        j.text = f'Rolling on Runway at {bumps_1g_segment["VCAS"][i]} knots'
                    for j in row_case.iter('mass_case_name'):
                        j.text = bumps_1g_segment["Mass_Case"][i] +'Z'
                    for j in row_case.iter('horizontal_speed'):
                        j.text = str(bumps_1g_segment["VCAS"][i])
                    for j in row_case.iter('maneuver_number'):
                        j.text = str(bumps_1g_segment["Segment_ID"][0][0])+'1'+str(cntr+1)

        
                    root.append(row_case)
                    cntr+=1
                    
                    name = "FZ1"+str(bumps_1g_segment["Segment_ID"][0][0])+str(bumps_1g_segment["Mission_ID"][0][0])+'xx'
                    if bumps_FZ1_sumry_flag == 0:
                        bumps_FZ1_sumry_flag = 1
                        self.__soldyn_sumry("\n"+f"{std_name} - {name}" +"\n")
                        self.__soldyn_sumry(f"{output_file_name}\n\n")
                    self.__soldyn_sumry(f"Case {cntr}:\n")
                    self.__soldyn_sumry(f"maneuver_name = Rolling on Runway at {bumps_1g_segment['VCAS'][i]} knots\n")
                    self.__soldyn_sumry(f"maneuver_number = {bumps_1g_segment['Segment_ID'][0][0]}1{cntr}\n")
                    self.__soldyn_sumry(f"mass_case_name = {bumps_1g_segment['Mass_Case'][i]}Z\n")

                    self.__soldyn_sumry(f"horizontal_speed = {bumps_1g_segment['VCAS'][i]}\n")
                    

            
                root.find('Number_of_Cases').text = str(len(root.findall('Calculation_Case')))
        
                et_str = ET.tostring(root, encoding='utf-8', method='xml')
                root = etree.fromstring(et_str)
                self.__closing_tags(root)

        
                with open(output_file_name,'wb') as f:
                    f.write(etree.tostring(root, pretty_print=True))
                    self.__logger.info(f"{output_file_name} created successfully.")
                self.__shell_scripting(row_case, bumps_1g_input_files, output_file_name)
        else:
            self.__logger.warning(f"1g takeoff for {std_name} group is empty.")
            print(f"1g takeoff for {std_name} group is empty.")


    def __change_permissions_recursive(self, directory):
        for dirpath, dirnames, filenames in os.walk(directory):
            # Change permissions for directories
            for dirname in dirnames:
                dir_full_path = os.path.join(dirpath, dirname)
                os.chmod(dir_full_path, 0o777)  # Full permissions for directories

            # Change permissions for files
            for filename in filenames:
                file_full_path = os.path.join(dirpath, filename)
                os.chmod(file_full_path, 0o777)  # Full permissions for files
                
    
    
    def __batman_execution(self):
        
        if self.__BatmanFlag == 0 and self.__Batman_execFlag == 1:
            self.__logger.info("Batman_ExecFlag is 1 but BatmanFlag is 0. Please check the flags.")
        
        elif self.__BatmanFlag == 1 and self.__Batman_execFlag == 1:
            self.__logger.info("Shell scripts execution for BATMAN started.")
            for i in range(len(self.__batman_exec_path_list)):
                script_path = self.__batman_exec_path_list[i]
                try:
                    subprocess.run([script_path], check=True)
                    self.__logger.info(f"Shell script:{script_path} executed successfully.")
                    print(f"Shell script:{script_path} executed successfully.")
                except subprocess.CalledProcessError as e:
                    self.__logger.error(f"Error executing shell script:{script_path}: {e}")
                    print(f"Error executing shell script:{script_path}: {e}")
            self.__logger.info("Shell scripts execution for BATMAN completed for all files.")
                
    def __soldyn_execution(self):
        if self.__SoldynFlag == 0 and self.__Soldyn_execFlag == 1:
            self.__logger.info("Soldyn_ExecFlag is 1 but SoldynFlag is 0. Please check the flags.")
        
        elif self.__SoldynFlag == 0 and self.__Soldyn_execFlag == 1:
            self.__logger.info("Shell scripts execution for SOLDYN started.")
            for i in range(len(self.__soldyn_exec_path_list)):
                script_path = self.__soldyn_exec_path_list[i]
                try:
                    subprocess.run([script_path], check=True)
                    self.__logger.info(f"Shell script:{script_path} executed successfully.")
                    print(f"Shell script:{script_path} executed successfully.")
                except subprocess.CalledProcessError as e:
                    self.__logger.error(f"Error executing shell script:{script_path}: {e}")
                    print(f"Error executing shell script:{script_path}: {e}")
            self.__logger.info("Shell scripts execution for SOLDYN completed for all files.")
    
    def run(self):
        self.__params_sumry_filename = str(self.__filename_issued(self.__output_dir+"/params_summary_", "", "", ".txt"))
        if self.__BatmanFlag == 1:
            self.__logger.info("Batman setup started.")
            print("Batman setup started.")
            self.batman()
            self.__logger.info("Batman setup completed and files are saved successfully.")
            print("Batman setup completed and files are saved successfully.")
        elif self.__BatmanFlag == 0:
            pass
        else:
            self.__logger.error("Please check the BatmanFlag")
            raise Exception("Please check the BatmanFlag")

        if self.__SoldynFlag == 1:
            self.__logger.info("Soldyn setup started.")
            print("Soldyn setup started.")
            if self.__BatmanFlag == 0:
                self.__grouping()
                
            path = self.__output_dir
            
            
            for i in range(len(self.__grouped_tables_names)):
                GroupExist = os.path.exists(path+"/"+ self.__grouped_std_names[i])
                if not GroupExist:
                    os.makedirs(path+"/"+ self.__grouped_std_names[i])
                self.__GroupPath = path+"/"+ self.__grouped_std_names[i]
                
                SoldynGroupExist = os.path.exists(path+"/"+ self.__grouped_std_names[i]+"/SOLDYN")
                if not SoldynGroupExist:
                    os.makedirs(path+"/"+ self.__grouped_std_names[i]+"/SOLDYN")
                self.__SoldynGroupPath = path+"/"+ self.__grouped_std_names[i]+"/SOLDYN"
                
                SoldynInputExist = os.path.exists(path+"/"+ self.__grouped_std_names[i]+"/SOLDYN"+"/Inputs")
                if not SoldynInputExist:
                    os.makedirs(path+"/"+ self.__grouped_std_names[i]+"/SOLDYN"+"/Inputs")
                self.__SoldynInputPath = path+"/"+ self.__grouped_std_names[i]+"/SOLDYN"+"/Inputs"
                SoldynOutputExist = os.path.exists(path+"/"+ self.__grouped_std_names[i]+"/SOLDYN"+"/Outputs")
                if not SoldynOutputExist:
                    os.makedirs(path+"/"+ self.__grouped_std_names[i]+"/SOLDYN"+"/Outputs")
                self.__SoldynOutputPath = path+"/"+ self.__grouped_std_names[i]+"/SOLDYN"+"/Outputs"
                
                SolstatGroupExist = os.path.exists(path+"/"+ self.__grouped_std_names[i]+"/SOLSTAT")
                if not SolstatGroupExist:
                    os.makedirs(path+"/"+ self.__grouped_std_names[i]+"/SOLSTAT")
                self.__SolstatGroupPath = path+"/"+ self.__grouped_std_names[i]+"/SOLSTAT"

                self.__logger.info(f"Soldyn setup for {self.__grouped_std_names[i]} group started.")
                print(f"Soldyn setup for {self.__grouped_std_names[i]} group started.")
                table = self.__grouped_tables[i].drop_duplicates().reset_index(drop=True)
                grouping_name = self.__grouped_tables_names[i]
                std_name = self.__grouped_std_names[i]
                soldyn_input_path = self.__SoldynInputPath
                self.soldyn_setup(table, soldyn_input_path,grouping_name, std_name)
                self.__logger.info(f"Soldyn setup for {std_name} group completed")
                print(f"Soldyn setup for {std_name} group completed")
            self.__logger.info("Soldyn setup is completed and all files are saved successfully.")
            print("Soldyn setup is completed and all files are saved successfully.")
        elif self.__SoldynFlag == 0:
            pass
        else:
            self.__logger.error("Please check the SoldynFlag")
            raise Exception("Please check the SoldynFlag")
            

        directory_path = self.__output_dir

        try:
            self.__change_permissions_recursive(directory_path)
            print(f"\nPermissions have been set to 777 for all files and directories in {directory_path}")
        except OSError as e:
            print(f"Error: {e}")
        
        
        self.__batman_execution()
        self.__soldyn_execution()
        
              
            
            
                
