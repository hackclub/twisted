import os
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.text import slugify

from ..models import UploadedFile

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
                uploaded_thru=request.POST.get("ref", "unknown"),
                filesize=file.size,
            )

            return JsonResponse(
                {
                    "status": "ok",
                    "link": url,
                    "name": filename,
                    "response": response_data,
                }
            )
        return JsonResponse(
            {"status": "error", "reason": "Invalid request: No file found"}
        )
    return JsonResponse(
        {"status": "error", "reason": "Invalid request: method not POST"}
    )


def file_uploader(request, image):
    """
    Basic imgur uploader return as json data.
    """
    try:
        ext = Path(image.name).suffix.lower()
        filename = (
            f"{uuid4()!s}-{image.size!s}/{slugify(Path(image.name).stem)}{ext}"
        )
        original_filename = Path(image.name).stem
        s3.upload_fileobj(
            image,
            os.environ["R2_BUCKET"],
            filename,
            ExtraArgs={
                "ContentType": image.content_type,
            },
        )

        return {
            "status": "ok",
            "link": f"{os.environ['R2_PUBLIC_URL']}{filename}",
            "name": original_filename,
            "size": image.size,
        }

    except (ClientError, BotoCoreError) as e:
        return {"status": "error", "error": str(e)}

    except Exception as e:
        return {
            "status": "error",
            "error": f"Unknown Error Occurred: {e!s}",
        }
