# OneForAll Docker local storage on Windows D:

This is an example override for Windows hosts that keep Docker's local data on drive D:.

## Option A: Keep the repository on D:
Clone the repository into `D:\\PROJECT\\OneForAll` and run Compose there. Bind mounts such as `.:/app` then refer to the repository on D:.

## Option B: Put OneForAll temporary and Redis data on D:
Set these variables in a local `.env` file (do not commit secrets):
```dotenv
ONEFORALL_DATA_DIR=D:/OneForAll/data
ONEFORALL_TEMP_DIR=D:/OneForAll/temp
```

Use the Compose override below, or copy these volume mappings into your Compose file:
```yaml
services:
  redis:
    volumes:
      - ${ONEFORALL_DATA_DIR:-D:/OneForAll/data}/redis:/data
  web:
    volumes:
      - .:/app
      - ${ONEFORALL_TEMP_DIR:-D:/OneForAll/temp}:/tmp/oneforall
  worker_convert:
    volumes:
      - .:/app
      - ${ONEFORALL_TEMP_DIR:-D:/OneForAll/temp}:/tmp/oneforall
  worker_image:
    volumes:
      - .:/app
      - ${ONEFORALL_TEMP_DIR:-D:/OneForAll/temp}:/tmp/oneforall
  worker_video:
    volumes:
      - .:/app
      - ${ONEFORALL_TEMP_DIR:-D:/OneForAll/temp}:/tmp/oneforall
  worker_gpu:
    volumes:
      - .:/app
      - ${ONEFORALL_TEMP_DIR:-D:/OneForAll/temp}:/tmp/oneforall
  beat:
    volumes:
      - .:/app
      - ${ONEFORALL_TEMP_DIR:-D:/OneForAll/temp}:/tmp/oneforall
```

Important:
- Create `D:\\OneForAll\\data\\redis` and `D:\\OneForAll\\temp` first, or allow Docker Desktop to create them.
- Ensure every container that writes temporary job files uses the same temp directory mapping.
- If a project container currently owns a named Redis volume, changing to a bind mount does not migrate existing Redis data automatically. Back up/export data first if it matters.
- This moves Compose-managed project data only. Docker image/build cache and Docker Desktop's own VM disk remain where Docker Desktop stores them. To relocate those, change Docker Desktop's disk image location in Settings > Resources > Advanced (wording may vary by version) and follow Docker's migration process.
- Do not move or delete Docker's internal folders manually while Docker Desktop is running.
