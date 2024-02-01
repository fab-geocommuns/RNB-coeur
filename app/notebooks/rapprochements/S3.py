import boto3
import os

def s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ.get("SCALEWAY_AWS_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("SCALEWAY_AWS_SECRET_KEY"),
        endpoint_url=os.environ.get("SCALEWAY_AWS_ENDPOINT_URL"),
        region_name=os.environ.get("SCALEWAY_AWS_REGION_NAME"),
    )

def download_from_s3(s3_path, local_path):
    if not os.path.isfile(local_path):
        s3 = s3_client()
        s3.download_file('rnb-open', s3_path, local_path)
    print("file is ready")
    return local_path

def upload_to_s3(local_file_path, s3_file_path):
    s3 = s3_client()
    
    with open(local_file_path, 'rb') as data:
        s3.upload_fileobj(data, 'rnb-open', s3_file_path)
    
    object_exists = s3.get_waiter("object_exists")
    object_exists.wait(Bucket='rnb-open', Key=s3_file_path)
    print("upload done")
