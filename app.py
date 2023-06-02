import datetime
import paho.mqtt.client as mqtt
import sqlite3
from flask import Flask, request, Response
import gpxpy
import gpxpy.gpx
import os
from peewee import *

database = SqliteDatabase('gps_data.db')
# 连接到数据库并创建表（如果不存在）
database.connect()

class GPSData(Model):
    timestamp = DateTimeField()
    latitude = FloatField()
    longitude = FloatField()

    class Meta:
        database = database

GPSData.create_table(safe=True)

def parse_data_and_store(data):
    # 解析数据
    parts = data.split(',')

    # 提取时间和日期信息
    time = parts[1][:6]
    date = parts[9]
    timestamp = datetime.datetime.strptime(f"{date} {time}", "%d%m%y %H%M%S")

    # 提取经纬度信息
    latitude = float(parts[3][:2]) + float(parts[3][2:]) / 60
    if parts[4] == 'S':
        latitude = -latitude

    longitude = float(parts[5][:3]) + float(parts[5][3:]) / 60
    if parts[6] == 'W':
        longitude = -longitude

    # 插入数据
    GPSData.create(timestamp=timestamp, latitude=latitude, longitude=longitude)


mqtt_host = os.environ.get('MQTT_HOST', '121.4.80.223')
mqtt_port = os.environ.get('MQTT_PORT', 1883)
mqtt_topic = os.environ.get('MQTT_TOPIC', '/gnss/864269067617379/up/nmea')

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.subscribe(mqtt_topic)  # 你需要将这里的主题替换为你的mqtt主题

def on_message(client, userdata, msg):
    gnrmc_data = msg.payload.decode()
    # 解析$GNRMC数据，获取时间和状态
    data_parts = gnrmc_data.split(',')
    if len(data_parts) < 10 or data_parts[0] != '$GNRMC':
        print('Invalid $GNRMC data: ' + gnrmc_data)
        return
    status = data_parts[2]
    # 如果状态是无效的，我们将跳过这个$GNRMC数据
    if status == 'V':
        print('Invalid GPS position: ' + gnrmc_data)
        return

    parse_data_and_store(gnrmc_data)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(mqtt_host, mqtt_port, 60)  # 你需要将mqtt_broker替换为你的mqtt broker的地址

# 循环处理mqtt消息
client.loop_start()

app = Flask(__name__)

@app.route('/get_gpx', methods=['GET'])
def get_gpx():
    # 从请求参数中获取开始时间和结束时间
    start_time = request.args.get('start_time', '')
    end_time = request.args.get('end_time', '')

    # 将字符串转换为 datetime.datetime 对象
    start_datetime = datetime.datetime.strptime(start_time, "%Y-%m-%d")
    end_datetime = datetime.datetime.strptime(end_time, "%Y-%m-%d")

    # 查询指定时间范围内的 GPS 数据
    query = GPSData.select().where((GPSData.timestamp >= start_datetime) & (GPSData.timestamp <= end_datetime))

    # 获取查询结果
    gps_data = list(query)

    # 创建GPX对象
    gpx = gpxpy.gpx.GPX()

    # 将$GNRMC数据转换为GPX格式
    for data in gps_data:
        time = data.timestamp
        latitude = str(data.latitude)
        longitude = str(data.longitude)

        # 创建新的航点
        wpt = gpxpy.gpx.GPXWaypoint()
        wpt.time = time
        wpt.latitude = latitude
        wpt.longitude = longitude

        # 将航点添加到GPX对象中
        gpx.waypoints.append(wpt)

    # 生成GPX格式的数据
    gpx_data = gpx.to_xml()

    # 通过接口返回GPX数据
    return Response(gpx_data, mimetype='application/gpx+xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
