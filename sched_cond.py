"""A generally useful event scheduler class.

Each instance of this class manages its own queue.
No multi-threading is implied; you are supposed to hack that
yourself, or use a single instance per application.

Each instance is parametrized with two functions, one that is
supposed to return the current time, one that is supposed to
implement a delay.  You can implement real-time scheduling by
substituting time and sleep from built-in module time, or you can
implement simulated time by writing your own functions.  This can
also be used to integrate scheduling with STDWIN events; the delay
function is allowed to modify the queue.  Time can be expressed as
integers or floating point numbers, as long as it is consistent.

Events are specified by tuples (time, priority, action, argument, kwargs).
As in UNIX, lower priority numbers mean higher priority; in this
way the queue can be maintained as a priority queue.  Execution of the
event means calling the action function, passing it the argument
sequence in "argument" (remember that in Python, multiple function
arguments are be packed in a sequence) and keyword parameters in "kwargs".
The action function may be an instance method so it
has another way to reference private data (besides global variables).
"""

import asyncio
import heapq
import time
import traceback
from collections import namedtuple

import threading
from time import monotonic as _time
from typing import Any, Callable, Coroutine, List, NamedTuple

__all__ = ["scheduler_condition"]


class Event(NamedTuple):
    """
    Event(time, priority, action, argument, kwargs)

    A named tuple representing a scheduled event.

    Attributes:
        time: Numeric type compatible with the return value of the timefunc function passed to the constructor.
        priority: Events scheduled for the same time will be executed in the order of their priority.
        action: Executing the event means executing action(*argument, **kwargs).
        argument: A sequence holding the positional arguments for the action.
        kwargs: A dictionary holding the keyword arguments for the action.
    """
    time: float
    priority: int
    action: Callable[..., Coroutine]
    argument: tuple
    kwargs: Any

    __slots__ = []

    def __eq__(self, o):
        return (self.time, self.priority) == (o.time, o.priority)

    def __lt__(self, o):
        return (self.time, self.priority) < (o.time, o.priority)

    def __le__(self, o):
        return (self.time, self.priority) <= (o.time, o.priority)

    def __gt__(self, o):
        return (self.time, self.priority) > (o.time, o.priority)

    def __ge__(self, o):
        return (self.time, self.priority) >= (o.time, o.priority)

_sentinel = object()


class scheduler_condition:

    def __init__(self, timefunc=_time, delayfunc=time.sleep):
        """Initialize a new instance, passing the time and delay
        functions"""
        self._queue: List[Event] = []
        self._lock = threading.Condition()
        # self._event = threading.Event()
        # self._running = True
        self.timefunc = timefunc
        self.delayfunc = delayfunc

        self.running_loop = asyncio.new_event_loop()

    def enterabs(self, time, priority, action: Callable[..., Coroutine], argument=(), kwargs=_sentinel):
        """Enter a new event in the queue at an absolute time.

        Returns an ID for the event which can be used to remove it,
        if necessary.

        """
        if kwargs is _sentinel:
            kwargs = {}
        event = Event(time, priority, action, argument, kwargs)
        with self._lock:
            heapq.heappush(self._queue, event)
            self._lock.notify()
        return event  # The ID

    def enter(self, delay, priority, action: Callable[..., Coroutine], argument=(), kwargs=_sentinel):
        """A variant that specifies the time as a relative time.

        This is actually the more commonly used interface.

        """
        time = self.timefunc() + delay
        return self.enterabs(time, priority, action, argument, kwargs)

    def cancel(self, event):
        """Remove an event from the queue.

        This must be presented the ID as returned by enter().
        If the event is not in the queue, this raises ValueError.

        """
        with self._lock:
            if event in self._queue:
                self._queue.remove(event)
            heapq.heapify(self._queue)
            # self._lock.notify()

    def empty(self):
        """Check whether the queue is empty."""
        with self._lock:
            return not self._queue

    def run(self):
        """Execute events until the queue is empty.
        If blocking is False executes the scheduled events due to
        expire soonest (if any) and then return the deadline of the
        next scheduled call in the scheduler.

        When there is a positive delay until the first event, the
        delay function is called and the event is left in the queue;
        otherwise, the event is removed from the queue and executed
        (its action function is called, passing it the argument).  If
        the delay function returns prematurely, it is simply
        restarted.

        It is legal for both the delay function and the action
        function to modify the queue or to raise an exception;
        exceptions are not caught but the scheduler's state remains
        well-defined so run() may be called again.

        A questionable hack is added to allow other threads to run:
        just after an event is executed, a delay of 0 is executed, to
        avoid monopolizing the CPU when other threads are also
        runnable.

        """
        # localize variable access to minimize overhead
        # and to improve thread safety
        lock = self._lock
        q = self._queue
        delayfunc = self.delayfunc
        timefunc = self.timefunc
        pop = heapq.heappop

        threading.Thread(target=self.running_loop.run_forever).start()

        while True:
            with lock:
                while not q:
                    self._lock.wait()
                time, priority, action, argument, kwargs = q[0]
                now = timefunc()
                # print(time, now)
                if time > now:
                    delay = True
                else:
                    delay = False
                    kwargs["event"] = pop(q)

            if delay:
                with lock:
                    self._lock.wait(time - now)
                # delayfunc(time - now)
            else:
                try:
                    self.running_loop.create_task(action(*argument, **kwargs))
                except Exception:
                    traceback.print_exc()
                delayfunc(0)  # Let other threads run
        self.running_loop.close()

    @property
    def queue(self):
        """An ordered list of upcoming events.

        Events are named tuples with fields for:
            time, priority, action, arguments, kwargs

        """
        # Use heapq to sort the queue rather than using 'sorted(self._queue)'.
        # With heapq, two events scheduled at the same time will show in
        # the actual order they would be retrieved.
        with self._lock:
            events = self._queue[:]
        return list(map(heapq.heappop, [events] * len(events)))
