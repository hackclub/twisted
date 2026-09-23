# twisted
[Twisted!!!](https://twisted.hackclub.com) Make cool projects and complete a twisted roadmap full of challenges to get your own PC!
<img width="2909" height="1369" alt="Screenshot_20260923-224353" src="https://github.com/user-attachments/assets/90e69116-cfa9-4004-b6ab-3d0221dd7949" />

## pages you need to see
- dashboard
- projects
- pathways
- refer
- docs
- admin (if you are an admin or you setup locally)

The whole website is built around a retro desktop UI, because the whole ysws is about getting a PC :D, includes a start menu, cool desktop windows, a cool background music playing and really great stuff giving you the desktop vibe.

## dev setup (local)
wanna help dev? follow these steps!
1. clone this repo
2. [install uv](https://docs.astral.sh/uv/getting-started/installation/)
3. copy twisted/.env.example to twisted/.env

### launching
1. run `cd twisted`
2. run `uv run manage.py migrate`
3. run `docker compose up db`
4. run `uv run manage.py tailwind dev` in a new terminal
5. 
## Thanks
Thats all! Thanks to Heliodex for making this Hack Club ysws possible, if your interested in participating, your're more than welcome to do that :)
