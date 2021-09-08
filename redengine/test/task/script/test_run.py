
# TODO
#import pytest
import multiprocessing
#
from redengine.tasks import PyScript
#from redengine.core.task.base import Task
#
import pandas as pd
import pytest
from textwrap import dedent


@pytest.mark.parametrize("execution", ["main", "thread", "process"])
@pytest.mark.parametrize(
    "script_path,expected_outcome,exc_cls",
    [
        pytest.param(
            "scripts/succeeding_script.py", 
            "success",
            None,
            id="Success"),
        pytest.param(
            "scripts/failing_script.py", 
            "fail", 
            RuntimeError,
            id="Failure"),
    ],
)
def test_run(tmpdir, script_files, script_path, expected_outcome, exc_cls, execution, session):
    kwargs = {"log_queue": multiprocessing.Queue(-1)} if execution == "process" else {}
    with tmpdir.as_cwd() as old_dir:

        task = PyScript(
            script_path, 
            name="a task",
            execution=execution
        )

        try:
            task(**kwargs)
        except:
            # failing execution="main"
            pass

        # Wait for finish
        if execution == "thread":
            while task.status == "run":
                pass
        elif execution == "process":
            # Do the logging manually
            que = kwargs["log_queue"]
            record = que.get(block=True, timeout=30)
            task.log_record(record)

        assert task.status == expected_outcome

        df = pd.DataFrame(session.get_task_log())
        records = df[["task_name", "action"]].to_dict(orient="records")
        assert [
            {"task_name": "a task", "action": "run"},
            {"task_name": "a task", "action": expected_outcome},
        ] == records


def test_run_specified_func(tmpdir, session):
    task_dir = tmpdir.mkdir("mytasks")
    task_dir.join("myfile.py").write(dedent("""
    def myfunc():
        pass
    """))

    with tmpdir.as_cwd() as old_dir:

        task = PyScript(
            "mytasks/myfile.py", 
            func="myfunc",
            name="a task",
            execution="main"
        )
        task()

        df = pd.DataFrame(session.get_task_log())
        records = df[["task_name", "action"]].to_dict(orient="records")
        assert [
            {"task_name": "a task", "action": "run"},
            {"task_name": "a task", "action": "success"},
        ] == records


def test_import_relative(tmpdir, session):
    task_dir = tmpdir.mkdir("mytasks")
    task_dir.join("myfile.py").write(dedent("""
    from utils import value
    def main():
        assert value == 5
    """))

    task_dir.join("utils.py").write(dedent("""
    value = 5
    """))

    with tmpdir.as_cwd() as old_dir:

        task = PyScript(
            "mytasks/myfile.py", 
            name="a task",
            execution="main"
        )
        task()

        df = pd.DataFrame(session.get_task_log())
        records = df[["task_name", "action"]].to_dict(orient="records")
        assert [
            {"task_name": "a task", "action": "run"},
            {"task_name": "a task", "action": "success"},
        ] == records

def test_import_package(tmpdir, session):
    pkg_dir = tmpdir.mkdir("mypkg")
    sub_dir = pkg_dir.mkdir("subpkg")
    util_dir = pkg_dir.mkdir("utils")

    pkg_dir.join("__init__.py").write("")
    sub_dir.join("__init__.py").write("")
    util_dir.join("__init__.py").write("from .util_file import value")

    sub_dir.join("myfile.py").write(dedent("""
    from mypkg.utils import value
    def main():
        assert value == 5
    """))

    util_dir.join("util_file.py").write("value = 5")

    with tmpdir.as_cwd() as old_dir:

        task = PyScript(
            "mypkg/subpkg/myfile.py", 
            name="a task",
            execution="main"
        )
        task()

        df = pd.DataFrame(session.get_task_log())
        records = df[["task_name", "action"]].to_dict(orient="records")
        assert [
            {"task_name": "a task", "action": "run"},
            {"task_name": "a task", "action": "success"},
        ] == records

def test_import_relative_with_params(tmpdir, session):
    task_dir = tmpdir.mkdir("mytasks")
    task_dir.join("myfile.py").write(dedent("""
    from utils import value
    def main(val_5, optional=None):
        assert val_5 == 5
        assert optional is None
    """))

    task_dir.join("utils.py").write(dedent("""
    value = 5
    """))

    with tmpdir.as_cwd() as old_dir:

        task = PyScript(
            "mytasks/myfile.py", 
            name="a task",
            execution="main"
        )
        task(params={"val_5":5})

        df = pd.DataFrame(session.get_task_log())
        records = df[["task_name", "action"]].to_dict(orient="records")
        assert [
            {"task_name": "a task", "action": "run"},
            {"task_name": "a task", "action": "success"},
        ] == records

def test_additional_sys_paths(tmpdir, session):
    task_dir = tmpdir.mkdir("mytasks")
    task_dir.join("myfile.py").write(dedent("""
    from utils import value
    # "utils" is in subfolder/utils.py but it is put to sys.path

    def main(val_5, optional=None):
        assert val_5 == 5
        assert optional is None
    """))

    task_dir.mkdir("subfolder").mkdir("another").join("utils.py").write(dedent("""
    value = 5
    """))

    with tmpdir.as_cwd() as old_dir:

        task = PyScript(
            "mytasks/myfile.py", 
            name="a task",
            execution="main",
            sys_paths=["mytasks/subfolder/another"]
        )
        task(params={"val_5":5})

        df = pd.DataFrame(session.get_task_log())
        records = df[["task_name", "action"]].to_dict(orient="records")
        assert [
            {"task_name": "a task", "action": "run"},
            {"task_name": "a task", "action": "success"},
        ] == records

# Parametrization
def test_parametrization_runtime(tmpdir, script_files, session):
    with tmpdir.as_cwd() as old_dir:

        task = PyScript(
            "scripts/parameterized_script.py", 
            name="a task",
            execution="main"
        )

        task(params={"integer": 1, "string": "X", "optional_float": 1.1, "extra_parameter": "Should not be passed"})

        df = pd.DataFrame(session.get_task_log())
        records = df[["task_name", "action"]].to_dict(orient="records")
        assert [
            {"task_name": "a task", "action": "run"},
            {"task_name": "a task", "action": "success"},
        ] == records

def test_parametrization_local(tmpdir, script_files, session):
    with tmpdir.as_cwd() as old_dir:

        task = PyScript(
            "scripts/parameterized_script.py", 
            name="a task",
            parameters={"integer": 1, "string": "X", "optional_float": 1.1},
            execution="main"
        )

        task()

        df = pd.DataFrame(session.get_task_log())
        records = df[["task_name", "action"]].to_dict(orient="records")
        assert [
            {"task_name": "a task", "action": "run"},
            {"task_name": "a task", "action": "success"},
        ] == records

def test_parametrization_kwargs(tmpdir, script_files, session):
    with tmpdir.as_cwd() as old_dir:

        task = PyScript(
            "scripts/parameterized_kwargs_script.py", 
            name="a task",
            parameters={"integer": 1, "string": "X", "optional_float": 1.1},
            execution="main"
        )

        task()

        df = pd.DataFrame(session.get_task_log())
        records = df[["task_name", "action"]].to_dict(orient="records")
        assert [
            {"task_name": "a task", "action": "run"},
            {"task_name": "a task", "action": "success"},
        ] == records