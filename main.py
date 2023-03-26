# gstreamer python bindings
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib



# os
import sys
import os

# concurrency and multi-processing 
import asyncio
from multiprocessing import Process, Queue

# Nats
from nats.aio.client import Client as NATS
import nats
# json
import json
# datetime
from pytz import timezone
import time
from datetime import datetime 
import imageio
import subprocess as sp
import torch

# cv
import numpy as np
import cv2
import io

#.env vars loaded
from os.path import join, dirname
from dotenv import load_dotenv
import ast
import gc
import psutil


from pytorchvideo.models.hub import slowfast_r50_detection
from yolo_slowfast.deep_sort.deep_sort import DeepSort
# from memory_profiler import profile












#to fetch data from postgres
from db_fetch import fetch_db
from db_fetch_members import fetch_db_mem


from lmdb_list_gen import attendance_lmdb_known, attendance_lmdb_unknown
from facedatainsert_lmdb import add_member_to_lmdb
from anamoly_track import trackmain
from project_1_update_ import output_func
# obj_model = torch.hub.load('ultralytics/yolov5', 'custom', path='./three_class_05_dec.pt')

obj_model = torch.hub.load('Detection', 'custom', path='./three_class_05_dec.pt', source='local',force_reload=True)
deepsort_tracker = DeepSort("./yolo_slowfast/deep_sort/deep_sort/deep/checkpoint/ckpt.t7")
device = 'cuda'
video_model = slowfast_r50_detection(True).eval().to(device)


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

nc_client = NATS() # global Nats declaration
Gst.init(sys.argv) # Initializes Gstreamer, it's variables, paths

# creation of directories for file storage
path = "./Mp4_output"
hls_path = "./Hls_output"
gif_path = "./Gif_output"

if os.path.exists(path) is False:
    os.mkdir(path)
    
if os.path.exists(hls_path) is False:
    os.mkdir(hls_path)
    
if os.path.exists(gif_path) is False:
    os.mkdir(gif_path)

# list variables
frames = []
numpy_frames = []
global known_whitelist_faces, known_blacklist_faces
known_whitelist_faces = []
known_whitelist_id = []
known_blacklist_faces = []
known_blacklist_id = []
cid_unpin_cnt = 0
gif_cid_list = []
# flag variable
start_flag = True
image_count = 0
track_type = []

def remove_cnts(folder):
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print('Failed to delete %s. Reason: %s' % (file_path, e))


def load_lmdb_list():

    known_whitelist_faces1, db_count_whitelist = attendance_lmdb_known()
    known_blacklist_faces1, db_count_blacklist = attendance_lmdb_unknown()
    
    global known_whitelist_faces
    known_whitelist_faces = known_whitelist_faces1
    
    global known_blacklist_faces
    known_blacklist_faces = known_blacklist_faces1

    print("-------------------------------------------------------------------------")
    print("-------------------------------------------------------------------------")
    print("-------------------------------------------------------------------------")
    print(len(known_whitelist_faces), len(known_blacklist_faces))
    print("-------------------------------------------------------------------------")
    print("-------------------------------------------------------------------------")
    print("-------------------------------------------------------------------------")

async def json_publish_activity(primary):    
    nc = await nats.connect(servers=["nats://216.48.181.154:5222"] , reconnect_time_wait= 50 ,allow_reconnect=True, connect_timeout=20, max_reconnect_attempts=60)
    js = nc.jetstream()
    JSONEncoder = json.dumps(primary)
    json_encoded = JSONEncoder.encode()
    Subject = "service.activities"
    Stream_name = "services"
    # await js.add_stream(name= Stream_name, subjects=[Subject])
    ack = await js.publish(Subject, json_encoded)
    print(f'Ack: stream={ack.stream}, sequence={ack.seq}')
    print("Activity is getting published")


def activity_trackCall(source, device_data):
    device_id = device_data[0]
    device_urn = device_data[1]
    timestampp = device_data[2]
    queue1 = Queue()

    trackmain(
        source, 
        device_id, 
        queue1, 
        obj_model,
        deepsort_tracker,
        video_model,
        device
        )

    video_data = queue1.get()

    # print(video_data)

    outt_ = output_func(video_data)
    outt_['deviceid'] = device_id
    outt_['timestamp'] = timestampp
    outt_['geo'] = {"latitude":'12.913632983105556', "longitude":'77.58994246818435'}
    pid = psutil.Process()
    memory_bytes = pid.memory_info().rss
    memory_mb = memory_bytes / 1024 / 1024
    mbb = f"{memory_mb:.2f}"
    outt_['memory'] = str(float(mbb) / 1024) + " GB"
    outt_["version"] = "v0.0.2"   
    print(outt_)
    if outt_['metaData']['detect']>0:    
        asyncio.run(json_publish_activity(primary=outt_)) 
    torch.cuda.empty_cache()    
    
    torch.cuda.empty_cache()
    pid = os.getpid()
    print("killing ",str(pid))
    sp.getoutput("kill -9 "+str(pid))

def config_func(source, device_data):
    print("success")
    device_id = device_data[0]
    urn = device_data[1]
    timestampp = device_data[2]
    subsciptions = device_data[3]
    print(subsciptions)
    # if "activity" in subsciptions:
    activity_trackCall(source, device_data)
    # activity_trackCall(source, device_data)
    print("^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^")


async def device_snap_pub(device_id, urn, gif_cid, time_stamp):
    nc = await nats.connect(servers=["nats://216.48.181.154:5222"] , reconnect_time_wait= 50 ,allow_reconnect=True, connect_timeout=20, max_reconnect_attempts=60)
    js = nc.jetstream()
    device_data = {
        "deviceId": device_id,
        "urn": urn,
        "timestamp": time_stamp,
        "thumbnail": gif_cid,
        # "uri": "https://hls.ckdr.co.in/live/stream1/1.m3u8",
        # "status": "active" 
    }
    JSONEncoder = json.dumps(device_data)
    json_encoded = JSONEncoder.encode()
    print(json_encoded)
    print("Json encoded")
    Subject = "service.device_thumbnail"
    Stream_name = "service"
    # await js.add_stream(name= Stream_name, subjects=[Subject])
    ack = await js.publish(Subject, json_encoded)
    print(f'Ack: stream={ack.stream}, sequence={ack.seq}')
    print("Thumbnail is getting published")


def numpy_creation(device_id, urn, img_arr, timestamp,device_data):

    global image_count, cid_unpin_cnt
    
    # filename for mp4
    # video_name_gif = gif_path + '/' + str(device_id)
    # if not os.path.exists(video_name_gif):
    #     os.makedirs(video_name_gif, exist_ok=True)
    
    # path = video_name_gif + '/' + str(timestamp).replace(' ','') + '.gif'
    
    image_count += 1
    if (image_count < 31):
        numpy_frames.append(img_arr)
    elif (image_count >= 31):
        print(timestamp)
        print("Images added: ", len(numpy_frames))
        # print(len(numpy_frames))
        Process(target = config_func,args = (numpy_frames, device_data,)).start()
        # config_func(numpy_frames, device_data)
        image_count = 0
        numpy_frames.clear()
        
        

        # with imageio.get_writer(path, mode="I") as writer:
        #     for idx, frame in enumerate(frames):
        #         print("Adding frame to GIF file: ", idx + 1)
        #         writer.append_data(frame)
                
        # print("PATH:", path)
        # command = 'ipfs --api={ipfs_url} add {file_path} -Q'.format(ipfs_url=ipfs_url, file_path=src_file)
        # gif_cid = sp.getoutput(command)
        # print(gif_cid)

        # # cid_unpin_cnt = cid_unpin_cnt + 1

        # # if len(gif_cid_list) < 50:
        # #     gif_cid_list.append(gif_cid)
        # # else:
        # #     #remove gif_cid_list[0] from ipfs
        # #     outt = sp.getoutput('ipfs --api=/ip4/216.48.181.154/tcp/5001 pin rm {cidd}'.format(cidd = gif_cid))
        # #     print(outt)
        # #     gif_cid_list.pop(0)
        # #     gif_cid_list.append(gif_cid)
        # # print(cid_unpin_cnt)
        # # if cid_unpin_cnt == 50:
        # #     print("deleting.")
        # #     sp.getoutput('ipfs --api=/ip4/216.48.181.154/tcp/5001 repo gc')
            

        # os.remove(path)
        # print("The path has been removed")
        # # await device_snap_pub(device_id = device_id, urn=urn, gif_cid = gif_cid, time_stamp = timestamp)
        # asyncio.run(device_snap_pub(device_id = device_id, urn=urn, gif_cid = gif_cid, time_stamp = timestamp))
        
        # frames.clear()
        # image_count = 0

def gif_creation(device_id, urn, img_arr, timestamp):

    global image_count, gif_path, cid_unpin_cnt
    
    # filename for mp4
    video_name_gif = gif_path + '/' + str(device_id)
    if not os.path.exists(video_name_gif):
        os.makedirs(video_name_gif, exist_ok=True)
    
    path = video_name_gif + '/' + str(timestamp).replace(' ','') + '.gif'
    
    image_count += 1
    if (image_count < 30):
        frames.append(img_arr)
    elif (image_count >= 30):
        print(timestamp)
        print("Images added: ", len(frames))
        print("Saving GIF file")
        with imageio.get_writer(path, mode="I") as writer:
            for idx, frame in enumerate(frames):
                print("Adding frame to GIF file: ", idx + 1)
                writer.append_data(frame)
                
        print("PATH:", path)
        command = 'ipfs --api={ipfs_url} add {file_path} -Q'.format(ipfs_url=ipfs_url, file_path=src_file)
        gif_cid = sp.getoutput(command)
        print(gif_cid)

        # cid_unpin_cnt = cid_unpin_cnt + 1

        # if len(gif_cid_list) < 50:
        #     gif_cid_list.append(gif_cid)
        # else:
        #     #remove gif_cid_list[0] from ipfs
        #     outt = sp.getoutput('ipfs --api=/ip4/216.48.181.154/tcp/5001 pin rm {cidd}'.format(cidd = gif_cid))
        #     print(outt)
        #     gif_cid_list.pop(0)
        #     gif_cid_list.append(gif_cid)
        # print(cid_unpin_cnt)
        # if cid_unpin_cnt == 50:
        #     print("deleting.")
        #     sp.getoutput('ipfs --api=/ip4/216.48.181.154/tcp/5001 repo gc')
            

        os.remove(path)
        print("The path has been removed")
        # await device_snap_pub(device_id = device_id, urn=urn, gif_cid = gif_cid, time_stamp = timestamp)
        asyncio.run(device_snap_pub(device_id = device_id, urn=urn, gif_cid = gif_cid, time_stamp = timestamp))
        
        frames.clear()
        image_count = 0

def gst_gif(device_id, device_info):
    
    location = device_info['rtsp'] # Fetching device info
    username = device_info['username']
    password = device_info['password']
    subscriptions = device_info['subscriptions']
    encode_type = device_info['videoEncodingInformation']
    urn = device_info['urn']
    
    print("Entering Gif Stream")
    
    def gst_to_opencv(sample):
        buf = sample.get_buffer()
        caps = sample.get_caps()
                    
        arr = np.ndarray(
            (caps.get_structure(0).get_value('height'),
            caps.get_structure(0).get_value('width')),
            buffer=buf.extract_dup(0, buf.get_size()),
            dtype=np.uint8)

        return arr

    def new_buffer(sink, data):
        global image_arr
        sample = sink.emit("pull-sample")
        buffer = sample.get_buffer()
        arr = gst_to_opencv(sample)
        rgb_frame = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        datetime_ist = str(datetime.now(timezone("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M:%S.%f'))
        # print("FRAME: ", type(rgb_frame))
        gif_creation(device_id=device_id, urn=urn, img_arr=rgb_frame, timestamp=datetime_ist)    
        return Gst.FlowReturn.OK
    
    try:
        if((encode_type.lower()) == "h264"):
            pipeline = Gst.parse_launch('rtspsrc name=g_rtspsrc_{device_id} location={location} latency=30 protocols="tcp" drop-on-latency=true !  rtph264depay name=g_depay_{device_id} ! h264parse config_interval=-1 name=g_parse_{device_id} ! decodebin name=g_decode_{device_id} ! appsink name=g_sink_{device_id}'.format(location=location, device_id = device_id))
        elif((encode_type.lower()) == "h265"):
            pipeline = Gst.parse_launch('rtspsrc name=g_rtspsrc_{device_id} location={location} latency=30 protocols="tcp" drop-on-latency=true !  rtph265depay name=g_depay_{device_id} ! h265parse config_interval=-1 name=g_parse_{device_id} ! decodebin name=g_decode_{device_id} ! appsink name=g_sink_{device_id}'.format(location=location, device_id = device_id))
            
        if not pipeline:
            print("Not all elements could be created.")
        else:
            print("All elements are created and launched sucessfully!")
        
        # sink params
        sink = pipeline.get_by_name('g_sink_{device_id}'.format(device_id = device_id))
        
        sink.set_property("emit-signals", True)
        sink.connect("new-sample", new_buffer, device_id)
        
        # Start playing
        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.SUCCESS:
            print("Able to set the pipeline to the playing state.")
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set the pipeline to the playing state.")
            
    except TypeError as e:
        print(TypeError," gstreamer Gif error >> ", e)       

def gst_hls(device_id, device_info):
        
    location = device_info['rtsp'] # Fetching device info
    username = device_info['username']
    password = device_info['password']
    subscriptions = device_info['subscriptions']
    encode_type = device_info['videoEncodingInformation']
    urn = device_info['urn']
    
    print("Entering HLS Stream")
    
    # filename for hls
    video_name_hls = hls_path + '/' + str(device_id)
    if not os.path.exists(video_name_hls):
        os.makedirs(video_name_hls, exist_ok=True)
    print(video_name_hls)
        
    try:
        if((encode_type.lower()) == "h264"):
            pipeline = Gst.parse_launch('rtspsrc name=h_rtspsrc_{device_id} location={location} latency=10 protocols="tcp" drop-on-latency=true ! rtph264depay name=h_depay_{device_id} ! decodebin name=h_decode_{device_id} ! videoconvert name=h_videoconvert_{device_id} ! videoscale name=h_videoscale_{device_id} ! video/x-raw,width=1920, height=1080 ! x264enc bitrate=512 name=h_enc_{device_id} ! mpegtsmux name=h_mux_{device_id} ! hlssink name=h_sink_{device_id}'.format(device_id = device_id, location=location))
        elif((encode_type.lower()) == "h265"):
            pipeline = Gst.parse_launch('rtspsrc name=h_rtspsrc_{device_id} location={location} latency=10 protocols="tcp" drop-on-latency=true ! rtph265depay name=h_depay_{device_id} ! decodebin name=h_decode_{device_id} ! videoconvert name=h_videoconvert_{device_id} ! videoscale name=h_videoscale_{device_id} ! video/x-raw,width=1920, height=1080 ! x264enc bitrate=512 name=h_enc_{device_id} ! mpegtsmux name=h_mux_{device_id} ! hlssink name=h_sink_{device_id}'.format(device_id = device_id, location=location))

        # sink params
        sink = pipeline.get_by_name('h_sink_{device_id}'.format(device_id = device_id))

        # Location of the playlist to write
        sink.set_property('playlist-root', 'https://hls.ckdr.co.in/live/stream{device_id}'.format(device_id = device_id))
        # Location of the playlist to write
        sink.set_property('playlist-location', '{file_path}/{file_name}.m3u8'.format(file_path = video_name_hls, file_name = device_id))
        # Location of the file to write
        sink.set_property('location', '{file_path}/segment.%01d.ts'.format(file_path = video_name_hls))
        # The target duration in seconds of a segment/file. (0 - disabled, useful for management of segment duration by the streaming server)
        sink.set_property('target-duration', 10)
        # Length of HLS playlist. To allow players to conform to section 6.3.3 of the HLS specification, this should be at least 3. If set to 0, the playlist will be infinite.
        sink.set_property('playlist-length', 3)
        # Maximum number of files to keep on disk. Once the maximum is reached,old files start to be deleted to make room for new ones.
        sink.set_property('max-files', 6)
        
        if not sink or not pipeline:
            print("Not all elements could be created.")
        else:
            print("All elements are created and launched sucessfully!")

        # Start playing
        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.SUCCESS:
            print("Successfully set the pipeline to the playing state.")
            
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set the pipeline to the playing state.")
            
    except TypeError as e:
        print(TypeError," gstreamer hls streaming error >> ", e)

def gst_mp4(device_id, device_info):
    
    location = device_info['rtsp'] # Fetching device info
    # location = 'rtsp://admin:admin123@streams.ckdr.co.in:8554/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif'
    username = device_info['username']
    password = device_info['password']
    subscriptions = device_info['subscriptions']
    encode_type = device_info['videoEncodingInformation']
    # encode_type = 'H264'
    urn = device_info['urn']
    
    print("Entering Framewise Stream")
    
    def gst_to_opencv(sample):
        buf = sample.get_buffer()
        caps = sample.get_caps()
                    
        arr = np.ndarray(
            (caps.get_structure(0).get_value('height'),
            caps.get_structure(0).get_value('width')),
            buffer=buf.extract_dup(0, buf.get_size()),
            dtype=np.uint8)

        return arr

    def new_buffer(sink, data):
        global image_arr
        device_data = []
        device_data.append(device_id)
        device_data.append(urn)
        device_data.append(datetime.now(timezone("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M:%S.%f'))
        device_data.append(subscriptions)
        sample = sink.emit("pull-sample")
        buffer = sample.get_buffer()
        arr = gst_to_opencv(sample)
        rgb_frame = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        datetime_ist = str(datetime.now(timezone("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M:%S.%f'))
        # print("FRAME: ", type(rgb_frame))
        numpy_creation(device_id=device_id, urn=urn, img_arr=rgb_frame, timestamp=datetime_ist,device_data=device_data)    
        return Gst.FlowReturn.OK
    
    try:
        if((encode_type.lower()) == "h264"):
            pipeline = Gst.parse_launch('rtspsrc name=g_rtspsrc_{device_id} location={location} latency=30 protocols="tcp" drop-on-latency=true !  rtph264depay name=g_depay_{device_id} ! h264parse config_interval=-1 name=g_parse_{device_id} ! decodebin name=h_decode_{device_id} ! videoconvert name=h_videoconvert_{device_id} ! videoscale name=h_videoscale_{device_id} ! video/x-raw,width=1920, height=1080 ! appsink name=g_sink_{device_id}'.format(location=location, device_id = device_id))
        elif((encode_type.lower()) == "h265"):
            pipeline = Gst.parse_launch('rtspsrc name=g_rtspsrc_{device_id} location={location} latency=30 protocols="tcp" drop-on-latency=true !  rtph265depay name=g_depay_{device_id} ! h265parse config_interval=-1 name=g_parse_{device_id} ! decodebin name=h_decode_{device_id} ! videoconvert name=h_videoconvert_{device_id} ! videoscale name=h_videoscale_{device_id} ! video/x-raw,width=1920, height=1080 ! appsink name=g_sink_{device_id}'.format(location=location, device_id = device_id))
            
        if not pipeline:
            print("Not all elements could be created.")
        else:
            print("All elements are created and launched sucessfully!")
        
        # sink params
        sink = pipeline.get_by_name('g_sink_{device_id}'.format(device_id = device_id))
        
        sink.set_property("emit-signals", True)
        sink.connect("new-sample", new_buffer, device_id)
        
        # Start playing
        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.SUCCESS:
            print("Able to set the pipeline to the playing state.")
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set the pipeline to the playing state.")
            
    except TypeError as e:
        print(TypeError," gstreamer Gif error >> ", e)  
             
#@profile
def call_gstreamer(device_data):
    print("Got device info from DB")
    i = 0
    for key in device_data:
        i = i + 1
        if i < 2:
            print(device_data[key])
            Process(target = gst_mp4(key, device_data[key])).start()
            # gst_mp4(key, device_data[key])
        # Process(target = gst_hls(key, device_data[key])).start()
        # Process(target = gst_gif(key, device_data[key])).start()
        # gst_mp4(key, device_data[key])      
        # time.sleep(5)
        # if i == 1:
            

async def device_info(msg):
    # print(dir(msg))
    if msg.subject == "service.device_discovery":

        print("Received a Device data\n")  
        deviceInfo_raw = msg.data  # fetch data from msg
        print(deviceInfo_raw)
        deviceInfo_decode = deviceInfo_raw.decode("utf-8") # decode the data which is in bytes
        deviceInfo_json = json.loads(deviceInfo_decode) # load it as dict
        print(deviceInfo_json)
        deviceInfo_username = deviceInfo_json['username'] # fetch all the individual fields from the dict
        deviceInfo_password = deviceInfo_json['password']
        # deviceInfo_ip = deviceInfo_json['ddns']
        deviceInfo_port = deviceInfo_json['port']
        deviceInfo_rtsp = deviceInfo_json['rtsp']
        deviceInfo_encode = deviceInfo_json['videoEncodingInformation']
        deviceInfo_id = deviceInfo_json['deviceId']
        deviceInfo_urn = deviceInfo_json['urn']
        
        # Process(target = gst_mp4(deviceInfo_id, deviceInfo_json)).start() # process for Mp4 generation
        gst_mp4(deviceInfo_id, deviceInfo_json)

        # Process(target = gst_hls(deviceInfo_id, deviceInfo_json)).start() # process for HLS generation
        # gst_hls(deviceInfo_id, deviceInfo_json)
        
        # Process(target = gst_gif(deviceInfo_id, deviceInfo_json)).start() # process for Gif generation 
        # gst_gif(deviceInfo_id, deviceInfo_json)

    if msg.subject == "service.member_update":
        
        print(msg.data)   
        data = (msg.data)
        #print(data)
        data  = data.decode()
        data = json.loads(data)
        print(data)
        status = add_member_to_lmdb(data)
        if status:
            subject = msg.subject
            reply = msg.reply
            data = msg.data.decode()
            await nc_client.publish(msg.reply,b'ok')
            print("Received a message on '{subject} {reply}': {data}".format(
                subject=subject, reply=reply, data=data))
            # Process(target = activity_lmdb_known()).start()
            # Process(target = activity_lmdb_unknown()).start()
            # Process(target = attendance_lmdb_known()).start()
            # Process(target = attendance_lmdb_unknown()).start()
            load_lmdb_list()
#@profile
def load_lmdb_fst(mem_data):
    i = 0
    for each in mem_data:
        i = i+1
        if i < 5:
            add_member_to_lmdb(each)
            print("inserting ",each)
        # time.sleep(10)
        
    # load_lmdb_list()

#@profile
async def main():
    try:

        # load_lmdb_list()
        device_data = fetch_db()
        call_gstreamer(device_data)
        # remove_cnts("./lmdb")
        # print("removed lmdb contents")
        # mem_data = fetch_db_mem()
        # print(mem_data)
        # load_lmdb_fst(mem_data)

        await nc_client.connect(servers=nats_urls) # Connect to NATS cluster!
        print("Nats Connected successfully!\n")
        await nc_client.subscribe("service.*", cb=device_info) # Subscribe to the device topic and fetch data through callback
        print("Subscribed to the topic, now you'll start receiving the Device details!\n")

    except Exception as e:
        await nc_client.close() # Close NATS connection
        print("Nats encountered an error: \n", e)
# @profile
# def test():
#     print("test")

if __name__ == '__main__':
    torch.multiprocessing.set_start_method('spawn', force=True)
    loop = asyncio.get_event_loop()
    try :
        loop.run_until_complete(main())
        loop.run_forever()
    except RuntimeError as e:
        print("error ", e)
        print(torch.cuda.memory_summary(device=None, abbreviated=False), "cuda")
    # test()
