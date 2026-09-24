# twisted

## dev setup
wanna help dev?

follow these steps!

1. clone this repo
2. [install uv](https://docs.astral.sh/uv/getting-started/installation/)
3. copy twisted/.env.example to twisted/.env

### launching
1. run `cd twisted`
2. run `uv run manage.py migrate`
3. run `docker compose up db`
4. run `uv run manage.py tailwind dev` in a new terminal

### testing
1. run `cd twisted`
2. run `uv run manage.py test --settings mysite.test_settings`