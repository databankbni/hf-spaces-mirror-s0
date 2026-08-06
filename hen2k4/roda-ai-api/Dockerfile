# Dùng môi trường Python 3.9
FROM python:3.9

# Chuyển thư mục làm việc vào /code
WORKDIR /code

# Cài đặt thư viện hệ thống cần thiết cho OpenCV (YOLO rất cần cái này)
RUN apt-get update && apt-get install ffmpeg libsm6 libxext6  -y

# Copy danh sách thư viện và cài đặt
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy toàn bộ code và model của bạn vào thư mục /code
COPY . /code

# Mở cổng 7860 và chạy server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]