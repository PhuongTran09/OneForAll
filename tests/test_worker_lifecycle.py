import asyncio

from app.worker.lifecycle import (
    WorkerLoopManager,
    get_worker_loop_manager,
    on_worker_init,
    on_worker_shutdown,
    run_in_worker_loop,
)


def test_worker_loop_manager_lifecycle():
    mgr = WorkerLoopManager()
    assert not mgr.is_running
    assert mgr.loop is None

    # Start loop
    loop1 = mgr.start()
    assert mgr.is_running
    assert loop1 is not None
    assert not loop1.is_closed()

    # Idempotent start returns same loop
    loop2 = mgr.start()
    assert loop2 is loop1

    # Run coroutine
    async def sample_coro(val: int) -> int:
        await asyncio.sleep(0.01)
        return val * 2

    res = mgr.run(sample_coro(21))
    assert res == 42

    # Stop loop
    mgr.stop()
    assert not mgr.is_running
    assert mgr.loop is None


def test_run_in_worker_loop_helper():
    async def sample_coro() -> str:
        return "success"

    res = run_in_worker_loop(sample_coro())
    assert res == "success"

    mgr = get_worker_loop_manager()
    assert mgr.is_running


def test_worker_signals_lifecycle():
    # Calling on_worker_init should start manager without error
    on_worker_init()
    mgr = get_worker_loop_manager()
    assert mgr.is_running

    # Multiple runs
    async def coro(x: int) -> int:
        return x + 1

    assert mgr.run(coro(10)) == 11
    assert mgr.run(coro(20)) == 21

    # Calling on_worker_shutdown should cleanly shut down
    on_worker_shutdown()
    assert not mgr.is_running
