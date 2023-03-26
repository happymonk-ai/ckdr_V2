import math

global id
def output_func(my_list):
    
    frames=[]               # this variable will hold the frame_id of all the frames in which a atleast one detection was made"
    ids_to_be_monitored=[]  #re-id of all the person type detection with anamoly score>50
    frame_anamoly_wgt = []
    person_counts = {}
    vehicle_counts = {}
    object_counts = {}
    activity_dict = {}
    det_score_dict = {}
    temp_list=[]
    metaObj = []
    frame_cid = {}

    people_count_list =[]
    vehicle_count_list = []
    object_count_list = []
   
    person_ids = []
    vehicle_ids = []
    object_ids = []

    for item in my_list:
       for x in item:
        frame_anamoly_wgt.append(x['frame_anamoly_wgt'])
        frame_id = x['frame_id']
        detection_info = x['detection_info']
        if detection_info ==[]:
            continue
        else:
            frames.append(frame_id)
        person = 0
        vehicle = 0
        object = 0
        cid = x['cid']
        for detection in x['detection_info']:
            for key, value in detection.items():
                if value['type'] == 'Person':
                    person += 1
                    person_counts[frame_id] = person
                    if cid not in person_ids:
                        person_ids.append(cid)
                    frame_cid[key]=person_ids
                    
                    
                    person_counts[frame_id] = person
                elif value['type'] == 'Vehicle':
                       vehicle +=1
                       vehicle_counts[frame_id] = vehicle
                       if cid not in vehicle_ids:
                           vehicle_ids.append(cid)
                           
                       
                       frame_cid[key]=vehicle_ids
                       
                elif value['type'] == 'Elephant':
                       object +=1
                       object_counts[frame_id] = object 
                       if cid not in object_ids:
                           object_ids.append(cid)
                           
                       
                       frame_cid[key]=object_ids  




    temp = [key for elem in my_list for x in elem for detection in x['detection_info'] for key, values in detection.items() if values.get('type') == 'Person' and values.get('anamoly_score') is not None and values['anamoly_score'] > 50]
    for id in temp:
        if id not in ids_to_be_monitored:
            ids_to_be_monitored.append(id)





    vehicle_count = sum(vehicle_counts.values())  # this variable will hold the count of total vehicles detected overall
    person_count = sum(person_counts.values())  # this variable will hold the count of total person detected overall
    animal_count = sum(object_counts.values())  # this variable will hold the count of total elephants detected overall
    total_count = vehicle_count + person_count + animal_count
    
    

    frame_count_vehicle = len(vehicle_counts)  # this variable will hold the count of total frames in which vehicle was detected
    frame_count_person = len(person_counts)    # this variable will hold the count of total frames in which people were detected
    frame_count_animal = len(object_counts)    # this variable will hold the count of total frames in which elephant was detected
    frame_count = len(frames)
    


    # if frame_count != 0 and total_count > frame_count:
    #     detection_count = math.ceil(total_count / frame_count)
    # else :
    #     detection_count = 0
    if frame_count_vehicle != 0 and vehicle_count > frame_count_vehicle:
        avg_Batchcount_vehicle = math.ceil(vehicle_count / frame_count_vehicle)
    else :
        avg_Batchcount_vehicle = 0
    if frame_count_animal != 0 and animal_count > frame_count_animal:
        avg_Batchcount_animal = math.ceil(animal_count / frame_count_animal)
    else :
        avg_Batchcount_animal = 0
    if frame_count_person !=0 and person_count > frame_count_person:
        avg_Batchcount_person = math.ceil(person_count / frame_count_person)
    else :
        avg_Batchcount_person = 0

    total_add = avg_Batchcount_person + avg_Batchcount_animal +  avg_Batchcount_vehicle

    for x in my_list:
        for item in x:
            for detection in item['detection_info']:
                for key,values in detection.items():
                    detection_score = float(values.get('anamoly_score') or 0)
                    activity_score =  float(values.get('activity_score') or 0)
                    act_type = values.get('type')  
                    id = key  
                    if act_type == 'Person' and id not in people_count_list:
                        people_count_list.append(id)
                    if act_type == 'Vehicle' and id not in vehicle_count_list:
                        vehicle_count_list.append(id)
                    if act_type == 'Elephant' and id not in object_count_list:
                        object_count_list.append(id)
                    m = int(len(frame_cid[id]))
                    if m%2==0 and len(frame_cid[id])<2:
                        c_id = frame_cid[id][0]
                    if m%2==0 and len(frame_cid[id])>2:
                        i = int(m/2) + 1
                        c_id = frame_cid[id][i]
                    else:
                        i=int((m+1)/2)
                        c_id = frame_cid[id][i]                  
                    activity = values.get('activity')
                    if id in det_score_dict :
                        if detection_score not in det_score_dict[id]:
                            det_score_dict[id].append(detection_score)
                    else:
                        det_score_dict[id] = [detection_score]
                    if id in activity_dict:
                        if activity not in activity_dict[id]:
                                activity_dict[id].append(activity)
                    else:
                        activity_dict[id] = [activity]
                    act =   activity_dict[id]
                
                    det_score = det_score_dict[id]
                    temp = {
                                "type": act_type,
                                "detection_score": det_score,
                                "activity_score": activity_score,
                                "track": '',
                                "id": id,
                                "activity": act,
                                "detect_time": '',
                                "cids": c_id
                            } 
                    temp_list.append(temp)            
    
    for obj in temp_list:          #this make sures that only unique entries are in metaObj
        if obj not in metaObj:
            metaObj.append(obj)
    for items in metaObj:
        items['detection_score']=sum(items['detection_score'])/len(items['detection_score'])
           
    
    
    if len(people_count_list) ==1:
        count_p = len(people_count_list)
    else :
        count_p = avg_Batchcount_person
    
    if len(vehicle_count_list) == 1:
        count_v = len(vehicle_count_list)
    else :
        count_v = avg_Batchcount_vehicle
        
    if len(object_count_list) == 1:
        count_o = len(object_count_list)
    else:
         count_o = avg_Batchcount_animal
    
    count_all = count_o +count_v +count_p

   
    metaBatch = {
        "detect": (count_all),
        "Frame_anomaly_score" : frame_anamoly_wgt,
        "count": {"people_count": (count_p),
                  "vehicle_count": (count_v),
                  "ObjectCount" : (count_o),
                  },
        "ids_to_be_monitored": ids_to_be_monitored,
        "cid": "str(detected_img_cid)",
        "object": metaObj

    }

    primary = {
        "type": "activity",
        "deviceid": "",
        "batchid": "",
        "timestamp": "",
        "geo": {
            "latitude": "",
            "longitude": ""
        },
        "metaData": metaBatch
    }


    return primary

# print(output_func(my_list))