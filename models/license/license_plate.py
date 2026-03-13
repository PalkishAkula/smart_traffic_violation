import torch
from ultralytics import YOLO

DATA_YAML = "License-Plate-Recognition-6/data.yaml"

device = 0 if torch.cuda.is_available() else "cpu"

print("Using device:", device)

model = YOLO("yolov8n.pt")

model.train(
    data=DATA_YAML,
    epochs=20,
    imgsz=640,
    batch=16,
    device=device,
    workers=2,
    patience=10,
    name="traffic_violation_model"
)

print("Training finished.")


#https://universe.roboflow.com/oceanwaste-vnhmf/bike-number-plate-3yvst/browse?queryText=&pageSize=50&startingIndex=0&browseQuery=true