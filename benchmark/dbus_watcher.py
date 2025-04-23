import asyncio
import dataclasses
import typing
import dbus_next


@dataclasses.dataclass
class DbusWatcher:
    bus_type: dbus_next.BusType
    bus_name: str
    path: str
    interface: str
    signal: str
    _signals: list[typing.Any] = dataclasses.field(default_factory=list)
    _bus: None | dbus_next.aio.MessageBus = None
    _task: None | asyncio.Task = None

    def _record_signal(self, signal: typing.Any) -> None:
        self._signals.append(signal)

    @property
    def signals(self) -> tuple[typing.Any, ...]:
        return tuple(self._signals)

    async def __aenter__(self) -> None:
        self._bus = dbus_next.aio.MessageBus(bus_type=self.bus_type)
        await self._bus.connect()
        introspection = await self._bus.introspect(self.bus_name, self.path)
        proxy = self._bus.get_proxy_object(self.bus_name, self.path, introspection)
        interface = proxy.get_interface(self.interface)
        getattr(interface, "on_" + self.signal)(self._record_signal)
        self._task = asyncio.create_task(self._bus.wait_for_disconnect())

    async def __aexit__(
        self,
        exc_type: None | typing.Type[BaseException],
        exc_value: None | BaseException,
        traceback: typing.Any,
    ) -> None | bool:
        assert self._bus and self._task
        self._bus.disconnect()
        await self._task
        self._bus = None
        self._task = None
        return None


if __name__ == "__main__":
    import asyncio

    watcher = DbusWatcher(
        dbus_next.BusType.SYSTEM,
        "org.freedesktop.login1",
        "/org/freedesktop/login1",
        "org.freedesktop.login1.Manager",
        "prepare_for_sleep",
    )
    async def main() -> None:
        async with watcher:
            print("hi")
            proc = await asyncio.create_subprocess_exec(
                "sleep",
                "10",
            )
            await proc.wait()
            print("lo")
        print(watcher.signals)
    asyncio.run(main())
