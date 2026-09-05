import json
import os
import requests
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.shortcuts import render, redirect
from ..models import Project, UploadedFile
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify
import boto3
from pathlib import Path
from uuid import uuid4
from botocore.exceptions import ClientError, BotoCoreError

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY"],
    aws_secret_access_key=os.environ["R2_SECRET_KEY"],
    region_name="auto",
)

@login_required
def upload_file(request):
    if request.method == "POST":
        if "file" in request.FILES:
            file = request.FILES["file"]
            # The size limit is a server-side policy; never let the client raise it.
            max_file_mb = 10

            file_size_mb = file.size / (1024 * 1024)
            if file_size_mb > max_file_mb:
                return JsonResponse(
                    {"status": "error", "reason": f"File size exceeds {max_file_mb}MB!"}
                )

            response_data = file_uploader(request, file)
            # Handle upload errors
            if response_data.get("status") == "error":
                return JsonResponse(response_data)
            
            url = response_data["link"]
            filename = response_data["name"]
            UploadedFile.objects.create(
                uploaded_by=request.user,
                link=url,
                cdn_response=response_data,
                uploaded_thru=request.POST.get('ref', 'unknown'),
                filesize=file.size
            )
            
            return JsonResponse({
                "status": "ok",
                "link": url,
                "name": filename,
                "response": response_data,
            })
        return JsonResponse(
            {"status": "error", "reason": "Invalid request: No file found"}
        )
    return JsonResponse(
        {"status": "error", "reason": "Invalid request: method not POST"}
    )


def _upload_fileobj(fileobj, filename, content_type, size):
    try:
        ext = Path(filename).suffix.lower()
        stored_name = f"{str(uuid4())}-{size}/{slugify(Path(filename).stem)}{ext}"
        original_filename = Path(filename).stem
        s3.upload_fileobj(
            fileobj,
            os.environ["R2_BUCKET"],
            stored_name,
            ExtraArgs={
                "ContentType": content_type,
            },
        )

        return {
            "status": "ok",
            "link": f"{os.environ['R2_PUBLIC_URL']}{stored_name}",
            "name": original_filename,
            "size": size,
        }

    except (ClientError, BotoCoreError) as e:
        return {
                "status": "error",
                "error": str(e)
            }

    except Exception as e:
        return {
            "status": "error",
            "error": f"Unknown Error Occurred: {str(e)}",
        }


def file_uploader(request, image):
    """
    Basic imgur uploader return as json data.
    """
    return _upload_fileobj(image, image.name, image.content_type, image.size)
