import logging


class IDSLogger:

    @staticmethod
    def get_logger(name: str):
        logger = logging.getLogger(name)

        if logger.handlers:
            return logger

        logger.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "[%(asctime)s][%(levelname)s] %(name)s - %(message)s"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)

        return logger
