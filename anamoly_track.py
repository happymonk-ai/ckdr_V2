#import libraries
import numpy as np
import os,cv2,torch,random,warnings
warnings.filterwarnings("ignore",category=UserWarning)

from pytorchvideo.transforms.functional import (
    uniform_temporal_subsample,
    short_side_scale_with_boxes,
    clip_boxes_to_image,)
from torchvision.transforms._functional_video import normalize
from pytorchvideo.data.ava import AvaLabeledVideoFramePaths

import cv2
import numpy as np
import os
from pytz import timezone 
import subprocess as sp
from try_anamoly import anamoly_score_calculator, frame_weighted_avg
path = os.getcwd()



#.env vars loaded
import os
from os.path import join, dirname
from dotenv import load_dotenv
import ast
import gc

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

ipfs_url = os.getenv("ipfs")
nats_urls = os.getenv("nats")
nats_urls = ast.literal_eval(nats_urls)

pg_url = os.getenv("pghost")
pgdb = os.getenv("pgdb")
pgport = os.getenv("pgport")
pguser = os.getenv("pguser")
pgpassword = os.getenv("pgpassword")


known_whitelist_faces = []
known_whitelist_id = []
known_blacklist_faces = []
known_blacklist_id = []
frame_cnt = 0


def tensor_to_numpy(tensor):
    img = tensor.cpu().numpy().transpose((1, 2, 0))
    return img

def ava_inference_transform(clip, boxes,
    num_frames = 32, #if using slowfast_r50_detection, change this to 32, 4 for slow 
    crop_size = 640, 
    data_mean = [0.45, 0.45, 0.45], 
    data_std = [0.225, 0.225, 0.225],
    slow_fast_alpha = 4, #if using slowfast_r50_detection, change this to 4, None for slow
):
    boxes = np.array(boxes)
    roi_boxes = boxes.copy()
    clip = uniform_temporal_subsample(clip, num_frames)
    clip = clip.float()

    clip = clip / 255.0
    height, width = clip.shape[2], clip.shape[3]
    boxes = clip_boxes_to_image(boxes, height, width)
    clip, boxes = short_side_scale_with_boxes(clip,size=crop_size,boxes=boxes,)
    clip = normalize(clip,
        np.array(data_mean, dtype=np.float32),
        np.array(data_std, dtype=np.float32),) 
    boxes = clip_boxes_to_image(boxes, clip.shape[2],  clip.shape[3])
    if slow_fast_alpha is not None:
        fast_pathway = clip
        slow_pathway = torch.index_select(clip,1,
            torch.linspace(0, clip.shape[1] - 1, clip.shape[1] // slow_fast_alpha).long())
        clip = [slow_pathway, fast_pathway]
    
    return clip, torch.from_numpy(boxes), roi_boxes


def plot_one_box(x, img, color=[100,100,100], text_info="None",
                 velocity=None,thickness=1,fontsize=0.5,fontthickness=1):
    # Plots one bounding box on image img
    c1, c2 = (int(x[0]), int(x[1])), (int(x[2]), int(x[3]))
    cv2.rectangle(img, c1, c2, color, thickness, lineType=cv2.LINE_AA)
    t_size = cv2.getTextSize(text_info, cv2.FONT_HERSHEY_TRIPLEX, fontsize , fontthickness+2)[0]
    cv2.rectangle(img, c1, (c1[0] + int(t_size[0]), c1[1] + int(t_size[1]*1.45)), color, -1)
    cv2.putText(img, text_info, (c1[0], c1[1]+t_size[1]+2), 
                cv2.FONT_HERSHEY_TRIPLEX, fontsize, [255,255,255], fontthickness)
    return img


def deepsort_update(Tracker,pred,xywh,np_img):
    outputs = Tracker.update(xywh, pred[:,4:5],pred[:,5].tolist(),cv2.cvtColor(np_img,cv2.COLOR_BGR2RGB))
    return outputs


def save_yolopreds_tovideo(yolo_preds,id_to_ava_labels,color_map,output_video):
    global frame_cnt
    video_data = []
    frame_data = []
    for i, (im, pred) in enumerate(zip(yolo_preds.ims, yolo_preds.pred)):
        frame_cnt = frame_cnt + 1
        confff  =  yolo_preds.pandas().xyxy[0]['confidence'].tolist()
        im=cv2.cvtColor(im,cv2.COLOR_BGR2RGB)
        if pred.shape[0]:
            for j, (*box, cls, trackid, vx, vy) in enumerate(pred):
                if int(cls) != 0:
                    ava_label = ''
                elif trackid in id_to_ava_labels.keys():
                    ava_label = id_to_ava_labels[trackid].split(' ')[0]
                else:
                    ava_label = 'Unknow'
                cd = int(trackid)
                detect_obj = yolo_preds.names[int(cls)]
                labells = ava_label
                # print(trackid,ava_label)
                text = '{} {} {}'.format(int(trackid),yolo_preds.names[int(cls)],ava_label) #[int(cls)]
                if len(confff) == len(pred):
                    people = {cd: {'type': detect_obj, 'activity': labells,"confidence":yolo_preds.pandas().xyxy[0]["confidence"].tolist()[j]}}
                else:
                    people = {cd: {'type': detect_obj, 'activity': labells,"confidence":0}}
                frame_data.append(people)
                # print(people)
                # print(text)
                color = color_map[int(cls)]
                # print(color)
                im = plot_one_box(box,im,color,text)
        cv2.imwrite("out.jpg",im)

        # print("frame_data",frame_data)
        frame_info_anamoly = anamoly_score_calculator(frame_data)

        frame_data.clear()
        # print(frame_data)
        # print("frame_info_anamoly",frame_info_anamoly)
        # anamoly_score_calculator(frame_data)
        frame_anamoly_wgt = frame_weighted_avg(frame_info_anamoly)
        # print(frame_info_anamoly)
        cidd = None
        if frame_info_anamoly != []:
            cv2.imwrite("cid_ref_image.jpg",im)
            command = 'ipfs --api={ipfs_url} add {file_path} -Q'.format(file_path="cid_ref_image.jpg",ipfs_url=ipfs_url)
            output = sp.getoutput(command)
            cidd = output
        video_data.append({"frame_id":frame_cnt,"frame_anamoly_wgt":frame_anamoly_wgt,"detection_info":frame_info_anamoly,"cid":cidd}) 
        output_video.write(im.astype(np.uint8))
    # print(frame_cnt)
    # print(video_data)

    return video_data

def get_length(filename):
    result = sp.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=sp.PIPE,
        stderr=sp.STDOUT)
    return float(result.stdout)

def trackmain(
    inputs,
    device_id ,
    queue1,
    obj_model,
    deepsort_tracker,
    video_model,
    device,
    conf = 0.4,
    classes = None,
    output = './output_model_.mp4',
    imsize = 640,
    iou = 0.4
):
    global frame_cnt
    frame_cnt = 0
    print("*****")
    print(len(inputs))
    print("*****")
    model = obj_model

    model.conf = conf

    model.iou = iou

    model.max_det = 200

    model.classes = classes


    ava_labelnames,_ = AvaLabeledVideoFramePaths.read_label_map("./yolo_slowfast/selfutils/temp.pbtxt")

    coco_color_map = [[random.randint(0, 255) for _ in range(3)] for _ in range(80)]

    vide_save_path = output 

    width,height = 1920,1080
    outputvideo = cv2.VideoWriter(vide_save_path,cv2.VideoWriter_fourcc(*'mp4v'), 25, (width,height))

    full_video_data = []

    video_clips = [torch.from_numpy(array).permute(2, 0, 1) for array in inputs]

    video_clips = torch.stack(video_clips)
    video_clips = video_clips.permute(1,0,2,3)

    img_num=video_clips.shape[1]
    # print(img_num)
    imgs=[]
    for j in range(img_num):
        imgs.append(tensor_to_numpy(video_clips[:,j,:,:]))

    imgs = inputs
    yolo_preds=model(imgs, size=imsize)

    for each in yolo_preds.ims:
        cv2.imwrite("test.jpg",each)

    deepsort_outputs=[]

    for j in range(len(yolo_preds.pred)):
        temp=deepsort_update(deepsort_tracker,yolo_preds.pred[j].cpu(),yolo_preds.xywh[j][:,0:4].cpu(),yolo_preds.ims[j])
        if len(temp)==0:
            temp=np.ones((0,8))

        deepsort_outputs.append(temp.astype(np.float32))
    yolo_preds.pred=deepsort_outputs

    id_to_ava_labels={}

    if yolo_preds.pred[img_num//2].shape[0]:

        inputs,inp_boxes,_= ava_inference_transform(video_clips,yolo_preds.pred[img_num//2][:,0:4],crop_size=imsize)
        inp_boxes = torch.cat([torch.zeros(inp_boxes.shape[0],1), inp_boxes], dim=1)
        if isinstance(inputs, list):
            inputs = [inp.unsqueeze(0).to(device) for inp in inputs]
        else:
            inputs = inputs.unsqueeze(0).to(device)
        with torch.no_grad():

            slowfaster_preds = video_model(inputs, inp_boxes.to(device))

            slowfaster_preds = slowfaster_preds.cpu()

        for tid,avalabel in zip(yolo_preds.pred[img_num//2][:,5].tolist(),np.argmax(slowfaster_preds,axis=1).tolist()):
            id_to_ava_labels[tid]=ava_labelnames[avalabel+1]

    video_data = save_yolopreds_tovideo(yolo_preds,id_to_ava_labels,coco_color_map,outputvideo)
    full_video_data.append(video_data)

        
    outputvideo.release()
    print('saved video to:', vide_save_path)
    queue1.put(full_video_data)
    
# if __name__=="__main__":
#     # trackmain("/home/nivetheni/backup-161/nivetheni/chokidr_v2/test_stand.mp4",3)