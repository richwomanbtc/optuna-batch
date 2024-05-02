import optuna


def objective(trial: optuna.trial.BaseTrial) -> float:
    x = trial.suggest_float("x", -100, 100)
    return (x - 2) ** 2


def create_study() -> optuna.study.Study:
    return optuna.create_study(
        direction="minimize",
        study_name="example_study",
    )
