"""python -m app.ml.train   (needs a seeded database: python -m data.seed)"""
from . import fraud, intent_model


def main() -> None:
    print("intent classifier:", intent_model.train_and_save())
    print("fraud model:      ", fraud.train_and_save())


if __name__ == "__main__":
    main()
