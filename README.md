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

All instructions below assume you've already cd'd into the `twisted` dir

### launching
1. run `uv run manage.py migrate`
2. run `docker compose up db`
3. run `uv run manage.py tailwind dev` in a new terminal

### getting an admin account
1. log into your account on the web
2. run `uv run manage.py shell_plus` or `uv run manage.py shell` depending on what you fancy
3. get your profile by running `profile = Profile.objects.get()` (assuming only one person has signed up)
4. run `profile.is_staff = True`
5. run `perms = ProfileStaffPermissions.objects.create(superuser = True, view_users = True, view_pathways = True, manage_pathways = True, manage_fulfillments = True, manage_shop = True, view_review = True, manage_review = True, manage_announcements = True, view_auditlogs = True)` (this creates a perms object with all perms)
6. run `profile.staff_permissions = perms` (this associates the perms object with your profile)
7. run `profile.save()` (this saves the changes to the DB)

### testing
run `uv run manage.py test --settings mysite.test_settings`
