from v2ray2proxy.base import V2RayProxy, V2RayCore
from asyncio import run
import logging, requests
from time import time

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=[logging.StreamHandler()])

# Test V2Ray link
TEST_LINK = "vless://cb5d5224-b21f-4522-b756-237205084ba9@94.103.169.120:51569?type=tcp&security=none#TelegramMask-rkn-sosat"


async def main():
    try:
        # Measure startup time
        start_time = time()
        logging.info("Initializing V2Ray...")
        proxy = V2RayProxy(TEST_LINK, socks_port=None)
        init_time = time()
        logging.info(f"V2Ray initialized in {init_time - start_time:.2f} seconds")

        # Measure check time
        check_start = time()
        logging.info("Checking V2Ray configuration...")
        with open("./v2ray_config.json", "w") as f:
            f.write(open(proxy.config_file_path, "r").read())
        check_end = time()
        logging.info(f"Configuration check completed in {check_end - check_start:.2f} seconds")

        # request_start = time()
        # requests.get(
        #     "https://api.ipify.org?format=json",
        #     proxies={"http": proxy.http_proxy_url, "https": proxy.http_proxy_url},
        #     timeout=30
        # )
        # request_end = time()
        # logging.info(f"request duration: {request_end - request_start:.2f} seconds")

        # Measure stop time
        stop_start = time()
        logging.info("Stopping V2Ray...")
        proxy.stop()
        stop_end = time()
        logging.info(f"V2Ray stopped in {stop_end - stop_start:.2f} seconds")

        logging.info(f"Test took {stop_end - start_time:.2f} seconds")

    except Exception as e:
        logging.error(f"Error during performance test: {e}")
        raise


if __name__ == "__main__":
    run(main())
