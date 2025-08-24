# yolo11_det.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Union
import cv2
import torch
from ultralytics import YOLO

PathStr = Union[str, Path]
InputSource = Union[PathStr, int]   # int 用于摄像头 ID


class YOLOv11Det:
    """
    全能 YOLOv11 检测封装类
    支持：单图 / 多图 / 视频 / 摄像头 / 网络流
    用法：
        det = YOLOv11Det("yolo11n.pt")
        det.predict("img.jpg")
        det.predict(["1.jpg", "2.jpg"])
        det.predict("videos/", save_img=True)
        det.predict(0)             # 摄像头
        det.predict("rtsp://xxx")
    """

    def __init__(self,
                 weight_path: PathStr,
                 device: str | None = None) -> None:
        weight_path = Path(weight_path)
        if not weight_path.exists():
            raise FileNotFoundError(weight_path)

        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.model = YOLO(str(weight_path)).to(self.device)
        print(f"[YOLOv11Det] model loaded: {weight_path} on {self.device}")

    @torch.no_grad()
    def predict(self,
                source: InputSource,
                conf: float = 0.25,
                iou: float = 0.45,
                save_img: bool = True,
                out_dir: PathStr = "runs/pred",
                **kwargs) -> List[Dict[str, Any]]:
        """
        :param source: 支持所有 YOLO 原生格式
        :param conf / iou: 阈值
        :param save_img: 是否保存画框结果（视频/摄像会保存为 .mp4）
        :param out_dir: 输出目录
        :param kwargs: 透传给 model.predict，如 imgsz、stream 等
        :return: List[Dict] 每张图/每帧的检测结果
        """
        out_dir = Path(out_dir)
        if save_img:
            out_dir.mkdir(parents=True, exist_ok=True)

        # 透传 ultralytics 原生参数
        results = self.model.predict(
            source=source,
            conf=conf,
            iou=iou,
            save=False,              # 我们自己控制保存
            device=self.device,
            **kwargs
        )

        all_dets = []
        for idx, r in enumerate(results):
            # 组装检测字典
            dets = []
            if r.boxes is not None:
                for box in r.boxes:
                    xyxy = box.xyxy[0].tolist()
                    cls_id = int(box.cls[0])
                    conf_score = float(box.conf[0])
                    dets.append({"xyxy": xyxy, "cls": cls_id, "conf": conf_score})

            # 保存画框图/视频帧
            if save_img:
                annotated = r.plot()
                if r.path:                # 图片/视频
                    save_path = out_dir / f"{Path(r.path).stem}_pred.jpg"
                    cv2.imwrite(str(save_path), annotated)
                else:                     # 摄像头或无路径 -> 用序号
                    save_path = out_dir / f"frame_{idx:08d}.jpg"
                    cv2.imwrite(str(save_path), annotated)

            all_dets.append({"source": str(r.path or idx), "detections": dets})

        return all_dets
