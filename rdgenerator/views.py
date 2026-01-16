import io
from pathlib import Path
import subprocess
import sys
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.core.files.base import ContentFile
import os
import re
import requests
import base64
import json
import uuid
import pyzipper
from django.conf import settings as _settings
from django.db.models import Q
from .forms import GenerateForm
from .models import GithubRun
from PIL import Image
from urllib.parse import quote

def _start_local_build(zip_path, myuuid, filename, platform, full_url):
    if platform != _settings.LOCAL_BUILD_PLATFORM:
        GithubRun.objects.filter(Q(uuid=myuuid)).update(
            status="local build supports windows only"
        )
        return False
    script_path = Path(_settings.BASE_DIR) / "scripts" / "build_windows_local.py"
    if not script_path.exists():
        GithubRun.objects.filter(Q(uuid=myuuid)).update(
            status="local build script missing"
        )
        return False
    log_dir = Path(_settings.LOCAL_BUILD_LOG_DIR) if _settings.LOCAL_BUILD_LOG_DIR else Path(_settings.BASE_DIR) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"build_{myuuid}.log"
    env = os.environ.copy()
    env["DCE_ZIP_PATH"] = str(Path(zip_path).resolve())
    env["DCE_UUID"] = myuuid
    env["DCE_FILENAME"] = filename
    env["DCE_PLATFORM"] = platform
    env["DCE_STATUS_URL"] = f"{full_url}/updategh"
    env["DCE_OUTPUT_DIR"] = str(Path(_settings.BASE_DIR) / "exe" / myuuid)
    env["DCE_ROOT"] = str(_settings.BASE_DIR)
    if _settings.LOCAL_BUILD_RUSTDESK_SRC:
        env["RUSTDESK_SRC"] = _settings.LOCAL_BUILD_RUSTDESK_SRC
    if _settings.LOCAL_BUILD_WORKTREE_ROOT:
        env["LOCAL_BUILD_WORKTREE_ROOT"] = _settings.LOCAL_BUILD_WORKTREE_ROOT
    with open(log_path, "wb") as log_handle:
        subprocess.Popen(
            [sys.executable, "-u", str(script_path)],
            cwd=str(_settings.BASE_DIR),
            env=env,
            stdout=log_handle,
            stderr=log_handle,
        )
    GithubRun.objects.filter(Q(uuid=myuuid)).update(status="local build started")
    return True

def generator_view(request):
    if request.method == 'POST':
        form = GenerateForm(request.POST, request.FILES)
        if form.is_valid():
            platform = form.cleaned_data['platform']
            version = form.cleaned_data['version']
            delayFix = form.cleaned_data['delayFix']
            cycleMonitor = form.cleaned_data['cycleMonitor']
            xOffline = form.cleaned_data['xOffline']
            hidecm = form.cleaned_data['hidecm']
            removeNewVersionNotif = form.cleaned_data['removeNewVersionNotif']
            server = form.cleaned_data['serverIP']
            key = form.cleaned_data['key']
            apiServer = form.cleaned_data['apiServer']
            urlLink = form.cleaned_data['urlLink']
            downloadLink = form.cleaned_data['downloadLink']
            if not server:
                server = 'rs-ny.rustdesk.com' #default rustdesk server
            if not key:
                key = 'OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw=' #default rustdesk key
            if not apiServer:
                apiServer = server+":21114"
            if not urlLink:
                urlLink = "https://rustdesk.com"
            if not downloadLink:
                downloadLink = "https://rustdesk.com/download"
            direction = form.cleaned_data['direction']
            installation = form.cleaned_data['installation']
            settings = form.cleaned_data['settings']
            appname = form.cleaned_data['appname']
            if not appname:
                appname = "rustdesk"
            filename = form.cleaned_data['exename']
            compname = form.cleaned_data['compname']
            if not compname:
                compname = "Purslane Ltd"
            androidappid = form.cleaned_data['androidappid']
            if not androidappid:
                androidappid = "com.carriez.flutter_hbb"
            compname = compname.replace("&","\\&")
            permPass = form.cleaned_data['permanentPassword']
            theme = form.cleaned_data['theme']
            themeDorO = form.cleaned_data['themeDorO']
            #runasadmin = form.cleaned_data['runasadmin']
            passApproveMode = form.cleaned_data['passApproveMode']
            denyLan = form.cleaned_data['denyLan']
            enableDirectIP = form.cleaned_data['enableDirectIP']
            #ipWhitelist = form.cleaned_data['ipWhitelist']
            autoClose = form.cleaned_data['autoClose']
            permissionsDorO = form.cleaned_data['permissionsDorO']
            permissionsType = form.cleaned_data['permissionsType']
            enableKeyboard = form.cleaned_data['enableKeyboard']
            enableClipboard = form.cleaned_data['enableClipboard']
            enableFileTransfer = form.cleaned_data['enableFileTransfer']
            enableAudio = form.cleaned_data['enableAudio']
            enableTCP = form.cleaned_data['enableTCP']
            enableRemoteRestart = form.cleaned_data['enableRemoteRestart']
            enableRecording = form.cleaned_data['enableRecording']
            enableBlockingInput = form.cleaned_data['enableBlockingInput']
            enableRemoteModi = form.cleaned_data['enableRemoteModi']
            removeWallpaper = form.cleaned_data['removeWallpaper']
            defaultManual = form.cleaned_data['defaultManual']
            overrideManual = form.cleaned_data['overrideManual']
            enablePrinter = form.cleaned_data['enablePrinter']
            enableCamera = form.cleaned_data['enableCamera']
            enableTerminal = form.cleaned_data['enableTerminal']

            if all(char.isascii() for char in filename):
                filename = re.sub(r'[^\w\s-]', '_', filename).strip()
                filename = filename.replace(" ","_")
            else:
                filename = "rustdesk"
            if not all(char.isascii() for char in appname):
                appname = "rustdesk"
            myuuid = str(uuid.uuid4())
            protocol = _settings.PROTOCOL
            host = request.get_host()
            full_url = f"{protocol}://{host}"
            try:
                iconfile = form.cleaned_data.get('iconfile')
                if not iconfile:
                    iconfile = form.cleaned_data.get('iconbase64')
                iconlink_url, iconlink_uuid, iconlink_file = save_png(iconfile,myuuid,full_url,"icon.png")
            except:
                print("failed to get icon, using default")
                iconlink_url = "false"
                iconlink_uuid = "false"
                iconlink_file = "false"
            try:
                logofile = form.cleaned_data.get('logofile')
                if not logofile:
                    logofile = form.cleaned_data.get('logobase64')
                logolink_url, logolink_uuid, logolink_file = save_png(logofile,myuuid,full_url,"logo.png")
            except:
                print("failed to get logo")
                logolink_url = "false"
                logolink_uuid = "false"
                logolink_file = "false"

            ###create the custom.txt json here and send in as inputs below
            decodedCustom = {}
            if direction != "Both":
                decodedCustom['conn-type'] = direction
            if installation == "installationN":
                decodedCustom['disable-installation'] = 'Y'
            if settings == "settingsN":
                decodedCustom['disable-settings'] = 'Y'
            if appname.upper != "rustdesk".upper and appname != "":
                decodedCustom['app-name'] = appname
            decodedCustom['override-settings'] = {}
            decodedCustom['default-settings'] = {}
            if permPass != "":
                decodedCustom['password'] = permPass
            if theme != "system":
                if themeDorO == "default":
                    if platform == "windows-x86":
                        decodedCustom['default-settings']['allow-darktheme'] = 'Y' if theme == "dark" else 'N'
                    else:
                        decodedCustom['default-settings']['theme'] = theme
                elif themeDorO == "override":
                    if platform == "windows-x86":
                        decodedCustom['override-settings']['allow-darktheme'] = 'Y' if theme == "dark" else 'N'
                    else:
                        decodedCustom['override-settings']['theme'] = theme
            decodedCustom['enable-lan-discovery'] = 'N' if denyLan else 'Y'
            #decodedCustom['direct-server'] = 'Y' if enableDirectIP else 'N'
            decodedCustom['allow-auto-disconnect'] = 'Y' if autoClose else 'N'
            if permissionsDorO == "default":
                decodedCustom['default-settings']['access-mode'] = permissionsType
                decodedCustom['default-settings']['enable-keyboard'] = 'Y' if enableKeyboard else 'N'
                decodedCustom['default-settings']['enable-clipboard'] = 'Y' if enableClipboard else 'N'
                decodedCustom['default-settings']['enable-file-transfer'] = 'Y' if enableFileTransfer else 'N'
                decodedCustom['default-settings']['enable-audio'] = 'Y' if enableAudio else 'N'
                decodedCustom['default-settings']['enable-tunnel'] = 'Y' if enableTCP else 'N'
                decodedCustom['default-settings']['enable-remote-restart'] = 'Y' if enableRemoteRestart else 'N'
                decodedCustom['default-settings']['enable-record-session'] = 'Y' if enableRecording else 'N'
                decodedCustom['default-settings']['enable-block-input'] = 'Y' if enableBlockingInput else 'N'
                decodedCustom['default-settings']['allow-remote-config-modification'] = 'Y' if enableRemoteModi else 'N'
                decodedCustom['default-settings']['direct-server'] = 'Y' if enableDirectIP else 'N'
                decodedCustom['default-settings']['verification-method'] = 'use-permanent-password' if hidecm else 'use-both-passwords'
                decodedCustom['default-settings']['approve-mode'] = passApproveMode
                decodedCustom['default-settings']['allow-hide-cm'] = 'Y' if hidecm else 'N'
                decodedCustom['default-settings']['allow-remove-wallpaper'] = 'Y' if removeWallpaper else 'N'
                decodedCustom['default-settings']['enable-remote-printer'] = 'Y' if enablePrinter else 'N'
                decodedCustom['default-settings']['enable-camera'] = 'Y' if enableCamera else 'N'
                decodedCustom['default-settings']['enable-terminal'] = 'Y' if enableTerminal else 'N'
            else:
                decodedCustom['override-settings']['access-mode'] = permissionsType
                decodedCustom['override-settings']['enable-keyboard'] = 'Y' if enableKeyboard else 'N'
                decodedCustom['override-settings']['enable-clipboard'] = 'Y' if enableClipboard else 'N'
                decodedCustom['override-settings']['enable-file-transfer'] = 'Y' if enableFileTransfer else 'N'
                decodedCustom['override-settings']['enable-audio'] = 'Y' if enableAudio else 'N'
                decodedCustom['override-settings']['enable-tunnel'] = 'Y' if enableTCP else 'N'
                decodedCustom['override-settings']['enable-remote-restart'] = 'Y' if enableRemoteRestart else 'N'
                decodedCustom['override-settings']['enable-record-session'] = 'Y' if enableRecording else 'N'
                decodedCustom['override-settings']['enable-block-input'] = 'Y' if enableBlockingInput else 'N'
                decodedCustom['override-settings']['allow-remote-config-modification'] = 'Y' if enableRemoteModi else 'N'
                decodedCustom['override-settings']['direct-server'] = 'Y' if enableDirectIP else 'N'
                decodedCustom['override-settings']['verification-method'] = 'use-permanent-password' if hidecm else 'use-both-passwords'
                decodedCustom['override-settings']['approve-mode'] = passApproveMode
                decodedCustom['override-settings']['allow-hide-cm'] = 'Y' if hidecm else 'N'
                decodedCustom['override-settings']['allow-remove-wallpaper'] = 'Y' if removeWallpaper else 'N'
                decodedCustom['override-settings']['enable-remote-printer'] = 'Y' if enablePrinter else 'N'
                decodedCustom['override-settings']['enable-camera'] = 'Y' if enableCamera else 'N'
                decodedCustom['override-settings']['enable-terminal'] = 'Y' if enableTerminal else 'N'

            for line in defaultManual.splitlines():
                k, value = line.split('=')
                decodedCustom['default-settings'][k.strip()] = value.strip()

            for line in overrideManual.splitlines():
                k, value = line.split('=')
                decodedCustom['override-settings'][k.strip()] = value.strip()
            
            decodedCustomJson = json.dumps(decodedCustom)

            string_bytes = decodedCustomJson.encode("ascii")
            base64_bytes = base64.b64encode(string_bytes)
            encodedCustom = base64_bytes.decode("ascii")

            # #github limits inputs to 10, so lump extras into one with json
            # extras = {}
            # extras['genurl'] = _settings.GENURL
            # #extras['runasadmin'] = runasadmin
            # extras['urlLink'] = urlLink
            # extras['downloadLink'] = downloadLink
            # extras['delayFix'] = 'true' if delayFix else 'false'
            # extras['dce'] = 'true'
            # extras['cycleMonitor'] = 'true' if cycleMonitor else 'false'
            # extras['xOffline'] = 'true' if xOffline else 'false'
            # extras['removeNewVersionNotif'] = 'true' if removeNewVersionNotif else 'false'
            # extras['compname'] = compname
            # extras['androidappid'] = androidappid
            # extra_input = json.dumps(extras)

            ####from here run the github action, we need user, repo, access token.
            if platform == 'windows':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-windows.yml/dispatches'
            if platform == 'windows-x86':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-windows-x86.yml/dispatches'
            elif platform == 'linux':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-linux.yml/dispatches'
            elif platform == 'android':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-android.yml/dispatches'
            elif platform == 'macos':
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-macos.yml/dispatches'
            else:
                url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-windows.yml/dispatches'

            #url = 'https://api.github.com/repos/'+_settings.GHUSER+'/rustdesk/actions/workflows/test.yml/dispatches'  
            inputs_raw = {
                "server":server,
                "key":key,
                "apiServer":apiServer,
                "custom":encodedCustom,
                "uuid":myuuid,
                "iconlink_url":iconlink_url,
                "iconlink_uuid":iconlink_uuid,
                "iconlink_file":iconlink_file,
                "logolink_url":logolink_url,
                "logolink_uuid":logolink_uuid,
                "logolink_file":logolink_file,
                "appname":appname,
                "genurl":_settings.GENURL,
                "urlLink":urlLink,
                "downloadLink":downloadLink,
                "delayFix": 'true' if delayFix else 'false',
                "dce":'true',
                "cycleMonitor": 'true' if cycleMonitor else 'false',
                "xOffline": 'true' if xOffline else 'false',
                "removeNewVersionNotif": 'true' if removeNewVersionNotif else 'false',
                "compname": compname,
                "androidappid":androidappid,
                "filename":filename
            }

            temp_json_path = f"data_{uuid.uuid4()}.json"
            zip_filename = f"secrets_{uuid.uuid4()}.zip"
            zip_path = "temp_zips/%s" % (zip_filename)
            Path("temp_zips").mkdir(parents=True, exist_ok=True)

            with open(temp_json_path, "w") as f:
                json.dump(inputs_raw, f)

            with pyzipper.AESZipFile(zip_path, 'w', compression=pyzipper.ZIP_LZMA, encryption=pyzipper.WZ_AES) as zf:
                zf.setpassword(_settings.ZIP_PASSWORD.encode())
                zf.write(temp_json_path, arcname="secrets.json")

            # 4. Cleanup the plain JSON file immediately
            if os.path.exists(temp_json_path):
                os.remove(temp_json_path)

            zipJson = {}
            zipJson['url'] = full_url
            zipJson['file'] = zip_filename

            zip_url = json.dumps(zipJson)

            data = {
                "ref":_settings.GHBRANCH,
                "inputs":{
                    "version":version,
                    "zip_url":zip_url
                }
            } 
            #print(data)
            headers = {
                'Accept':  'application/vnd.github+json',
                'Content-Type': 'application/json',
                'Authorization': 'Bearer '+_settings.GHBEARER,
                'X-GitHub-Api-Version': '2022-11-28'
            }
            create_github_run(myuuid)
            if _settings.LOCAL_BUILD:
                started = _start_local_build(zip_path, myuuid, filename, platform, full_url)
                status = "local build started" if started else "local build failed to start"
                return render(request, 'waiting.html', {'filename':filename, 'uuid':myuuid, 'status':status, 'platform':platform})
            response = requests.post(url, json=data, headers=headers)
            print(response)
            if 200 <= response.status_code < 300:
                return render(request, 'waiting.html', {'filename':filename, 'uuid':myuuid, 'status':"正在启动生成器……请稍候", 'platform':platform})
            else:
                if _settings.DEBUG_API_RESPONSE:
                    return JsonResponse({
                        "error": "Something went wrong",
                        "status_code": response.status_code,
                        "response_text": response.text
                    })
                else:
                    return JsonResponse({"error": "Something went wrong"})
    else:
        form = GenerateForm()
    #return render(request, 'maintenance.html')
    return render(request, 'generator.html', {'form': form})


def check_for_file(request):
    filename = request.GET['filename']
    uuid = request.GET['uuid']
    platform = request.GET['platform']
    gh_run = GithubRun.objects.filter(Q(uuid=uuid)).first()
    status = gh_run.status if gh_run else "waiting"
    output_dir = Path("exe") / uuid
    has_any = False
    has_exe = False
    has_msi = False
    if output_dir.is_dir():
        for item in output_dir.iterdir():
            if not item.is_file():
                continue
            has_any = True
            if item.name == f"{filename}.exe":
                has_exe = True
            if item.name == f"{filename}.msi":
                has_msi = True
    if has_any:
        return render(request, 'generated.html', {
            'filename': filename,
            'uuid': uuid,
            'platform': platform,
            'has_exe': has_exe,
            'has_msi': has_msi,
        })
    return render(request, 'waiting.html', {'filename':filename, 'uuid':uuid, 'status':status, 'platform':platform})


def download(request):
    filename = request.GET['filename']
    uuid = request.GET['uuid']
    #filename = filename+".exe"
    file_path = os.path.join('exe',uuid,filename)
    with open(file_path, 'rb') as file:
        response = HttpResponse(file, headers={
            'Content-Type': 'application/vnd.microsoft.portable-executable',
            'Content-Disposition': f'attachment; filename="{filename}"'
        })

    return response

def get_png(request):
    filename = request.GET['filename']
    uuid = request.GET['uuid']
    #filename = filename+".exe"
    file_path = os.path.join('png',uuid,filename)
    with open(file_path, 'rb') as file:
        response = HttpResponse(file, headers={
            'Content-Type': 'application/vnd.microsoft.portable-executable',
            'Content-Disposition': f'attachment; filename="{filename}"'
        })

    return response

def create_github_run(myuuid):
    new_github_run = GithubRun(
        uuid=myuuid,
        status="正在启动生成器……请稍候"
    )
    new_github_run.save()

def update_github_run(request):
    data = json.loads(request.body)
    myuuid = data.get('uuid')
    mystatus = data.get('status')
    GithubRun.objects.filter(Q(uuid=myuuid)).update(status=mystatus)
    return HttpResponse('')

def resize_and_encode_icon(imagefile):
    maxWidth = 200
    try:
        with io.BytesIO() as image_buffer:
            for chunk in imagefile.chunks():
                image_buffer.write(chunk)
            image_buffer.seek(0)

            img = Image.open(image_buffer)
            imgcopy = img.copy()
    except (IOError, OSError):
        raise ValueError("Uploaded file is not a valid image format.")

    # Check if resizing is necessary
    if img.size[0] <= maxWidth:
        with io.BytesIO() as image_buffer:
            imgcopy.save(image_buffer, format=imagefile.content_type.split('/')[1])
            image_buffer.seek(0)
            return_image = ContentFile(image_buffer.read(), name=imagefile.name)
        return base64.b64encode(return_image.read())

    # Calculate resized height based on aspect ratio
    wpercent = (maxWidth / float(img.size[0]))
    hsize = int((float(img.size[1]) * float(wpercent)))

    # Resize the image while maintaining aspect ratio using LANCZOS resampling
    imgcopy = imgcopy.resize((maxWidth, hsize), Image.Resampling.LANCZOS)

    with io.BytesIO() as resized_image_buffer:
        imgcopy.save(resized_image_buffer, format=imagefile.content_type.split('/')[1])
        resized_image_buffer.seek(0)

        resized_imagefile = ContentFile(resized_image_buffer.read(), name=imagefile.name)

    # Return the Base64 encoded representation of the resized image
    resized64 = base64.b64encode(resized_imagefile.read())
    #print(resized64)
    return resized64
 
#the following is used when accessed from an external source, like the rustdesk api server
def startgh(request):
    #print(request)
    data_ = json.loads(request.body)
    ####from here run the github action, we need user, repo, access token.
    url = 'https://api.github.com/repos/'+_settings.GHUSER+'/'+_settings.REPONAME+'/actions/workflows/generator-'+data_.get('platform')+'.yml/dispatches'  
    data = {
        "ref": _settings.GHBRANCH,
        "inputs":{
            "server":data_.get('server'),
            "key":data_.get('key'),
            "apiServer":data_.get('apiServer'),
            "custom":data_.get('custom'),
            "uuid":data_.get('uuid'),
            "iconlink":data_.get('iconlink'),
            "logolink":data_.get('logolink'),
            "appname":data_.get('appname'),
            "extras":data_.get('extras'),
            "filename":data_.get('filename')
        }
    } 
    headers = {
        'Accept':  'application/vnd.github+json',
        'Content-Type': 'application/json',
        'Authorization': 'Bearer '+_settings.GHBEARER,
        'X-GitHub-Api-Version': '2022-11-28'
    }
    response = requests.post(url, json=data, headers=headers)
    print(response)
    return HttpResponse(status=204)

def save_png(file, uuid, domain, name):
    file_save_path = "png/%s/%s" % (uuid, name)
    Path("png/%s" % uuid).mkdir(parents=True, exist_ok=True)

    if isinstance(file, str):  # Check if it's a base64 string
        try:
            header, encoded = file.split(';base64,')
            decoded_img = base64.b64decode(encoded)
            file = ContentFile(decoded_img, name=name) # Create a file-like object
        except ValueError:
            print("Invalid base64 data")
            return None  # Or handle the error as you see fit
        except Exception as e:  # Catch general exceptions during decoding
            print(f"Error decoding base64: {e}")
            return None
        
    with open(file_save_path, "wb+") as f:
        for chunk in file.chunks():
            f.write(chunk)
    # imageJson = {}
    # imageJson['url'] = domain
    # imageJson['uuid'] = uuid
    # imageJson['file'] = name
    #return "%s/%s" % (domain, file_save_path)
    return domain, uuid, name

def save_custom_client(request):
    file = request.FILES['file']
    myuuid = request.POST.get('uuid')
    file_save_path = "exe/%s/%s" % (myuuid, file.name)
    Path("exe/%s" % myuuid).mkdir(parents=True, exist_ok=True)
    with open(file_save_path, "wb+") as f:
        for chunk in file.chunks():
            f.write(chunk)

    return HttpResponse("File saved successfully!")

def cleanup_secrets(request):
    # Pass the UUID as a query param or in JSON body
    data = json.loads(request.body)
    my_uuid = data.get('uuid')
    
    if not my_uuid:
        return HttpResponse("Missing UUID", status=400)

    # 1. Find the files in your temp directory matching the UUID
    temp_dir = os.path.join('temp_zips')
    
    # We look for any file starting with 'secrets_' and containing the uuid
    for filename in os.listdir(temp_dir):
        if my_uuid in filename and filename.endswith('.zip'):
            file_path = os.path.join(temp_dir, filename)
            try:
                os.remove(file_path)
                print(f"Successfully deleted {file_path}")
            except OSError as e:
                print(f"Error deleting file: {e}")

    return HttpResponse("Cleanup successful", status=200)

def get_zip(request):
    filename = request.GET['filename']
    #filename = filename+".exe"
    file_path = os.path.join('temp_zips',filename)
    with open(file_path, 'rb') as file:
        response = HttpResponse(file, headers={
            'Content-Type': 'application/vnd.microsoft.portable-executable',
            'Content-Disposition': f'attachment; filename="{filename}"'
        })

    return response
