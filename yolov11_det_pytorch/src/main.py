from yolov11_det import YOLOv11Det

# ---------------- DEMO ----------------
if __name__ == "__main__":
    det = YOLOv11Det("./data/yolo11n.pt")

    # 1. 单张
    dets = det.predict("./data/xiaomi_su7.jpg")

    # 2. 多张
    # dets = det.predict(["1.jpg", "2.jpg"])

    # 3. 目录
    # dets = det.predict("images/")

    # 4. 视频
    # dets = det.predict("http://devimages.apple.com.edgekey.net/streaming/examples/bipbop_4x3/gear2/prog_index.m3u8", save_img=True)

    # 5. 摄像头
    # dets = det.predict(0, save_img=True)

    # 打印结果
    for item in dets:
        print(item["source"], item["detections"])