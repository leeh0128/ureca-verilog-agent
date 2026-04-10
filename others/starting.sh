# 1. in the local terminal @IIC-OSIC-TOOLS directory
docker run -d --name iic-osic-tools_xvnc_uid_1012 \
  -p 5903:5901 -p 8081:6080 \
  -v "$HOME/eda/designs":/foss/designs \
  -e VNC_PW=abc123 \
  hpretl/iic-osic-tools:latest

# 2. connect to the desktop using VNC Client (for my case - TigerVNC Viewer)
# VNC client: localhost:5903 (password abc123)
# Using TigerVNC, we will need to use the 5903 port in our local laptop:
ssh -L 5903:127.0.0.1:5903 -L 8081:127.0.0.1:8081 hyunseung@incypher-icd2

# 3. Opening dockerized environment bash in the terminal
docker exec -it iic-osic-tools_xvnc_uid_1012 bash
# or we can open in the VNC Viewer (TigerVNC for my case)

# 4. Shell inside the container (for the mux flow)
cd /foss/designs/mux4
make env          # see what it auto-detected
make all          # prep → RTL sim → synth (uses GF180 if found; otherwise generic)
make gls          # optional: gate-level simulation with GF180 sim model
make waves        # open GTKWave on RTL waves

# 4. Stop and remove the existing container (required since the name is taken)
docker rm -f iic-osic-tools_xvnc_uid_1012
