
from atlas.core import MultiScheduler
from atlas.task import FuncTask
from atlas.time import TimeDelta
from atlas.core.task.base import Task, clear_tasks, get_task
from atlas.conditions import SchedulerCycles, SchedulerStarted, TaskFinished, TaskStarted, AlwaysFalse, AlwaysTrue
from atlas.core.parameters import GLOBAL_PARAMETERS
from atlas import session
from atlas.session import session

import pytest
import logging
import sys
import time
import os

# TODO:
#   Test maintainer task 
#   Test parametrization (parameter passing)
#   Test scheduler crashing

# Task funcs
def run_failing():
    raise RuntimeError("Task failed")

def run_succeeding():
    pass

def run_slow():
    time.sleep(30)

def create_line_to_file():
    with open("work.txt", "a") as file:
        file.write("line created\n")

def run_with_param(int_5):
    assert int_5 == 5

def run_maintainer(_scheduler_):
    assert isinstance(_scheduler_, MultiScheduler)
    _scheduler_.name = "maintained scheduler"

def test_task_execution(tmpdir):
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        # To be confident the scheduler won't lie to us
        # we test the task execution with a job that has
        # actual measurable impact outside atlas
        scheduler = MultiScheduler(
            [
                FuncTask(create_line_to_file, name="add line to file"),
            ], 
            shut_condition=TaskStarted(task="add line to file") >= 3,
        )

        scheduler()

        with open("work.txt", "r") as file:
            assert 3 == len(list(file))


@pytest.mark.parametrize(
    "task_func,run_count,fail_count,success_count",
    [
        pytest.param(
            run_succeeding, 
            3, 0, 3,
            id="Succeeding task"),

        pytest.param(
            run_failing, 
            3, 3, 0,
            id="Failing task"),
    ],
)
def test_task_log(tmpdir, task_func, run_count, fail_count, success_count):
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        task = FuncTask(task_func, name="task")

        scheduler = MultiScheduler(
            [
                task,
            ], shut_condition=TaskStarted(task="task") >= run_count
        )
        scheduler()

        history = task.get_history()
        assert run_count == (history["action"] == "run").sum()
        assert success_count == (history["action"] == "success").sum()
        assert fail_count == (history["action"] == "fail").sum()


def test_task_fail_traceback(tmpdir):
    # There is a speciality in tracebacks in multiprocessing
    # See: https://bugs.python.org/issue34334
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        task = FuncTask(run_failing, name="task")

        scheduler = MultiScheduler(
            [
                task,
            ], shut_condition=TaskStarted(task="task") >= 3
        )
        scheduler()
        history = task.get_history()
        failures = history[history["action"] == "fail"]
        assert 3 == len(failures)

        for tb in failures["exc_text"]:
            assert "Traceback (most recent call last):" in tb
            assert "RuntimeError: Task failed" in tb


@pytest.mark.parametrize("state", [True, False])
def test_task_force_state(tmpdir, state):
    with tmpdir.as_cwd() as old_dir:
        session.reset()

        task = FuncTask(
            run_succeeding, 
            start_cond=AlwaysFalse() if state else AlwaysTrue(), 
            name="task"
        )
        task.force_state = state

        scheduler = MultiScheduler(
            [
                task,
            ], shut_condition=~SchedulerStarted(period=TimeDelta("1 second"))
        )
        scheduler()

        run_times = 1 if state else 0 

        history = task.get_history()
        assert run_times == (history["action"] == "run").sum()

        if state:
            # The force_state should have reseted as it should have run once
            assert task.force_state is None 
        else:
            # The force_state should still be False and the task should still not run
            assert task.force_state is False 


def test_task_timeout(tmpdir):
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        task = FuncTask(run_slow, name="slow task")

        scheduler = MultiScheduler(
            [
                task,
            ], 
            shut_condition=TaskStarted(task="slow task") >= 2,
            timeout="1 seconds"
        )
        scheduler()

        history = task.get_history()
        assert 2 == (history["action"] == "run").sum()
        assert 2 == (history["action"] == "terminate").sum()
        assert 0 == (history["action"] == "success").sum()
        assert 0 == (history["action"] == "fail").sum()


def test_priority(tmpdir):
    with tmpdir.as_cwd() as old_dir:
        session.reset()

        task_1 = FuncTask(run_succeeding, priority=1, name="first")
        task_2 = FuncTask(run_failing, priority=10, name="last")
        task_3 = FuncTask(run_failing, priority=5, name="second")
        scheduler = MultiScheduler(
            [
                task_1,
                task_2,
                task_3
            ], shut_condition=TaskStarted(task="last") >= 1
        )

        scheduler()
        assert scheduler.n_cycles == 1

        history = session.get_task_log()
        history = history.set_index("action")

        task_1_start = history[(history["task_name"] == "first")].loc["run", "asctime"]
        task_3_start = history[(history["task_name"] == "second")].loc["run", "asctime"]
        task_2_start = history[(history["task_name"] == "last")].loc["run", "asctime"]
        
        assert task_1_start < task_3_start < task_2_start

def test_pass_params_as_global(tmpdir):
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        task = FuncTask(run_with_param, name="parametrized")
        scheduler = MultiScheduler(
            [
                task,
            ], shut_condition=TaskStarted(task="parametrized") >= 1
        )

        # Passing global parameters
        session.parameters["int_5"] = 5
        session.parameters["extra_param"] = "something"

        scheduler()

        history = task.get_history()
        assert 1 == (history["action"] == "run").sum()
        assert 1 == (history["action"] == "success").sum()
        assert 0 == (history["action"] == "fail").sum()

    
def test_pass_params_as_local(tmpdir):
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        task = FuncTask(
            run_with_param, 
            name="parametrized", 
            parameters={"int_5": 5, "extra_param": "something"}
        )
        scheduler = MultiScheduler(
            [
                task,
            ], shut_condition=TaskStarted(task="parametrized") >= 1
        )

        scheduler()

        history = task.get_history()
        assert 1 == (history["action"] == "run").sum()
        assert 1 == (history["action"] == "success").sum()
        assert 0 == (history["action"] == "fail").sum()


def test_pass_params_as_local_and_global(tmpdir):
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        task = FuncTask(
            run_with_param, 
            name="parametrized", 
            parameters={"int_5": 5}
        )
        scheduler = MultiScheduler(
            [
                task,
            ], shut_condition=TaskStarted(task="parametrized") >= 1
        )

        # Additional parameters
        session.parameters["extra_param"] = "something"

        scheduler()

        history = task.get_history()
        assert 1 == (history["action"] == "run").sum()
        assert 1 == (history["action"] == "success").sum()
        assert 0 == (history["action"] == "fail").sum()


# Maintainer
def test_maintainer_task(tmpdir):
    with tmpdir.as_cwd() as old_dir:
        session.reset()
        # To be confident the scheduler won't lie to us
        # we test the task execution with a job that has
        # actual measurable impact outside atlas
        scheduler = MultiScheduler(
            tasks=[],
            maintainer_tasks=[
                FuncTask(run_maintainer, name="maintainer"),
            ], 
            shut_condition=TaskStarted(task="maintainer") >= 1,
            name="unmaintained scheduler"
        )

        scheduler()

        history = get_task("maintainer").get_history()
        assert 1 == (history["action"] == "run").sum()
        assert 1 == (history["action"] == "success").sum()
        assert 0 == (history["action"] == "fail").sum()

        assert scheduler.name == "maintained scheduler"