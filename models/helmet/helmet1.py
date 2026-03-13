
#install ultralytics
#to run this file 

from ultralytics import YOLO
import torch
import os

DATA_YAML = "/content/Helmet-and-Number-Plate-Detection-for-Motorbike-Safety-3/data.yaml"

if not os.path.exists(DATA_YAML):
    raise FileNotFoundError("Dataset YAML not found")

device = 0 if torch.cuda.is_available() else "cpu"

# Use larger model
model = YOLO("yolov8n.pt")   # Upgraded from yolov8n

model.train(
    data=DATA_YAML,
    epochs=40,              # Increased epochs
    imgsz=768,              # Larger image size (better small object detection)
    batch=16,
    device=device,
    workers=4,
    patience=20,
    optimizer="AdamW",
    lr0=0.001,
    lrf=0.01,
    cos_lr=True,            # Cosine learning rate
    weight_decay=0.0005,
    
    # Stronger Augmentation
    hsv_h=0.015,
    hsv_s=0.7,
    hsv_v=0.4,
    degrees=5.0,
    translate=0.1,
    scale=0.5,
    shear=2.0,
    mosaic=1.0,
    mixup=0.2,
    
    name="traffic_violation_improved",
    pretrained=True,
    verbose=True
)

print("Improved training completed")
#https://universe.roboflow.com/helmet-and-number-plate-detection-project/helmet-and-number-plate-detection-for-motorbike-safety-iityz