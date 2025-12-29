## Host the dce server with docker

1. First you will need to fork this repo on github
2. Next, setup a A Github fine-grained access token with permissions for your dce
   repository:
    * login to your github account  
    * click on your profile picture at the top right, click Settings  
    * at the bottom of the left panel, click Developer Settings  
    * click Personal access tokens  
    * click Fine-grained tokens  
    * click Generate new token  
    * give a token name, change expiration to whatever you want  
    * under Repository access, select Only select repositories, then pick your
      dce repo  
    * give Read and Write access to actions and workflows  
    * You might have to go to: https://github.com/USERNAME/dce/actions and hit green Enable Actions button so it works.
3. Next, login to your Github account, go to your dce repo page (https://github.com/USERNAME/dce)
   * Click on Settings
   * In the left pane, click on Secrets and variables, then click Actions
   * Now click New repository secret
   * Set the Name to GENURL
   * Set the Secret to the hostname or domain your server is accessed from
4. Now download the docker-compose.yml file and fill in the environment variables:
  * SECRET_KEY="your secret key" - generate a secret key by running: ```python3 -c 'import secrets; print(secrets.token_hex(100))'```
  * GHUSER="your github username"  
  * GHBEARER="your fine-grained access token"  
  * PROTOCOL="https" *optional - defaults to "https", change to "http" if you need to
  * REPONAME="dce" *optional - defaults to "dce", change this if you renamed the repo when you forked it
5. Now just run ```docker compose up -d```


## Host manually:

1. A Github account with a fork of this repo  
2. A Github fine-grained access token with permissions for your dce
   repository:
    * login to your github account  
    * click on your profile picture at the top right, click Settings  
    * at the bottom of the left panel, click Developer Settings  
    * click Personal access tokens  
    * click Fine-grained tokens  
    * click Generate new token  
    * give a token name, change expiration to whatever you want  
    * under Repository access, select Only select repositories, then pick your
      dce repo  
    * give Read and Write access to actions and workflows  
    * You might have to go to: https://github.com/USERNAME/dce/actions and hit green Enable Actions button so it works.
3. Setup environment variables/secrets:
    * environment variables on the server running dce:  
        * GHUSER="your github username"  
        * GHBEARER="your fine-grained access token"  
        * PROTOCOL="https" *optional - defaults to "https", change to "http" if you need to
        * REPONAME="dce" *optional - defaults to "dce", change this if you renamed the repo when you forked it
    * github secrets (setup on your github account for your dce repo):  
        * GENURL="example.com:8000"  *this is the domain and port that you are
          running dce on, needs to be accessible on the internet, depending
          on how you have this setup the port may not be needed  

```
# Open to the directory you want to install dce (change /opt to wherever you want)  
cd /opt

# Clone your dce repo, change Ghostdehole to your github username
git clone https://github.com/Ghostdehole/dce.git

# Open the dce directory
cd dce

# Setup a python virtual environment called dce
python -m venv .venv

# Activate the python virtual environment 
source .venv/bin/activate

# Install the python dependencies
pip install -r requirements.txt

# Setup the database
python manage.py migrate

# Run the server, change 8000 with whatever you want
python manage.py runserver 0.0.0.0:8000
```

open your web browser to yourdomain:8000

use nginx, caddy, traefik, etc. for ssl reverse proxy

### To autostart the server on boot, you can set up a systemd service called dce.service

replace user, group, and port if you need to  replace /opt with wherever you
have installed dce  save the following file as
/etc/systemd/system/dce.service, and make sure to change GHUSER, GHBEARER

```
[Unit]
Description=Rustdesk Client Generator
[Service]
Type=simple
LimitNOFILE=1000000
Environment="GHUSER=yourgithubusername"
Environment="GHBEARER=yourgithubtoken"
PassEnvironment=GHUSER GHBEARER
ExecStart=/opt/dce/.venv/bin/python3 /opt/dce/manage.py runserver 0.0.0.0:8000
WorkingDirectory=/opt/dce/
User=root
Group=root
Restart=always
StandardOutput=file:/var/log/dce.log
StandardError=file:/var/log/dce.error
# Restart service after 10 seconds if node service crashes
RestartSec=10
[Install]
WantedBy=multi-user.target
```

then run this to enable autostarting the service on boot, and then start it
manually this time:

```
sudo systemctl enable dce.service
sudo systemctl start dce.service
```
and to get the status of the server, run:
```
sudo systemctl status dce.service
```
