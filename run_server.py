import asyncio
from aiohttp import web
from aiohttp.web import Application, Response, json_response, View, HTTPUnprocessableEntity, HTTPNotFound
import aiohttp_cors
from aiohttp_sse import sse_response
import aioredis

from json import dumps
from itertools import cycle
from dateutil.parser import parse

loop = asyncio.get_event_loop()


async def devices(request):
    redis = request.app['redis']
    thingyset = await redis.smembers('thingy')
    return json_response(thingyset)

class ABCSensorView(View):
    def __init__(self, request):
        super().__init__(request)
        self.thingy_uuid = request.match_info['thingy_uuid']
        self.sensor = request.match_info.get('sensor')
        self.redis = request.app['redis']

class TSensorView(ABCSensorView):
    async def get(self):
        ws = web.WebSocketResponse()
        if ws.can_prepare(self.request):
            await ws.prepare(self.request)
            sub = self.request.app['sub']
            ch = (await sub.subscribe(self.thingy_uuid+':'+self.sensor))[0]
            while (await ch.wait_message()):
                data = await ch.get_json()
                await ws.send_json(data)
            return ws
        else:
            val = await self.redis.zrange(self.thingy_uuid+':'+self.sensor, -1, -1)
            try:
                return json_response(body=val[0])
            except IndexError:
                return HTTPNotFound(text='No {} sensor data found for {}'.format(self.sensor, self.thingy_uuid))

    async def post(self):
        data = await self.request.json()
        try:
            timestamp = int(parse(data['timestamp']).strftime('%s'))
        except KeyError:
            return HTTPUnprocessableEntity(text="Missing data for timestamp field.")
        except ValueError:
            return HTTPUnprocessableEntity(text="Not a valid datetime.")
        tr = self.redis.multi_exec()
        try:
            for sensor in data['sensors']:
                tr.zadd(self.thingy_uuid+':'+sensor, timestamp, dumps(data))
                self.redis.publish_json(self.thingy_uuid+':'+sensor, data)
        except KeyError:
            return HTTPUnprocessableEntity(text="Missing data for sensors field.")
        tr.sadd('thingy', self.thingy_uuid)
        await tr.execute()
        return json_response(data)

class SensorView(ABCSensorView):
    async def get(self):
        ws = web.WebSocketResponse()
        if ws.can_prepare(self.request):
            await ws.prepare(self.request)
            sub = self.request.app['sub']
            ch = (await sub.subscribe(self.thingy_uuid+':'+self.sensor))[0]
            while (await ch.wait_message()):
                data = await ch.get_json()
                await ws.send_json(data)
            return ws
        else:
            val = await self.redis.get(self.thingy_uuid+':'+self.sensor)
            if not val:
                return HTTPNotFound(reason='No {} sensor data found for {}'.format(self.sensor, self.thingy_uuid)) #TODO wrong type
            return json_response(body=val)

    async def put(self):
        data = await self.request.json()
        tr = self.redis.multi_exec()
        tr.set(self.thingy_uuid+':'+self.sensor, dumps(data))
        self.redis.publish_json(self.thingy_uuid+':'+self.sensor, data)
        tr.sadd('thingy', self.thingy_uuid)
        await tr.execute()
        return json_response(data)

async def setup(request):
    return json_response({
        'temperature': {'interval': 1000},
        'pressure': {'interval': 1000},
        'humidity': {'interval': 1000},
        'color': {'interval': 1000},
        'gas': {'mode': 1}
    })

class LEDCycle(object):
    def __init__(self, interval=1.):
        self.color_cycle = cycle(range(1,9))
        self.interval = interval
        self.tick = asyncio.Event()
        asyncio.ensure_future(self.clock())

    async def clock(self):
        while True:
            self.tick.clear()
            await asyncio.sleep(self.interval)
            self.led = self.__next__()
            self.tick.set()

    def __next__(self):
        return {
            'color': next(self.color_cycle),
            'intensity': 20,
            'delay': 1000
        }

    def __aiter__(self):
        return self

    async def __anext__(self):
        await self.tick.wait()
        return self.led

led_cycle = LEDCycle()

async def led(request):
    ws = web.WebSocketResponse()
    if ws.can_prepare(request):
        await ws.prepare(request)
        async for led in led_cycle:
            await ws.send_json(led)
        return ws
    else:
        if request.headers.get('Accept') == 'text/event-stream':
            async with sse_response(request) as resp:
                async for led in led_cycle:
                    resp.send(dumps(led))
            return resp
        else:
            return json_response(next(led_cycle))

async def init(loop):
    app = web.Application(loop=loop)
    app['redis'] = await aioredis.create_redis(
            ('localhost', 6379), encoding='utf-8', loop=loop)
    app['sub'] = await aioredis.create_redis(
            ('localhost', 6379), encoding='utf-8', loop=loop)
    # Configure default CORS settings.
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
            )
    })

    cors.add(app.router.add_get('/', devices))

    cors.add(app.router.add_route('get', '/{thingy_uuid}/sensors/{sensor:temperature|pressure|humidity|gas|color}', TSensorView))
    cors.add(app.router.add_route('post', '/{thingy_uuid}/sensors/', TSensorView))
    cors.add(app.router.add_route('get', '/{thingy_uuid}/sensors/{sensor:button}', SensorView))
    cors.add(app.router.add_route('put', '/{thingy_uuid}/sensors/{sensor:button}', SensorView))

    cors.add(app.router.add_get('/{thingy_uuid}/actuators/led', led))
    cors.add(app.router.add_get('/{thingy_uuid}/setup', setup))

    srv = await loop.create_server(app.make_handler(), '127.0.0.1', 8080)
    return srv

loop.run_until_complete(init(loop))

try:
    loop.run_forever()
except KeyboardInterrupt:
    pass
