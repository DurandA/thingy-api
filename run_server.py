import asyncio
from aiohttp import web
from aiohttp.web import Application, Response, json_response, HTTPNotAcceptable, View
from aiohttp_sse import sse_response
import aioredis

from json import dumps
from collections import defaultdict
from itertools import cycle

loop = asyncio.get_event_loop()


async def devices(request):
    redis = request.app['redis']
    return json_response(thingyset)
    thingyset = await redis.smembers('thingy')

async def sensors(request):
    pass

class SensorView(View):
    key = 'value'

    def __init__(self, request):
        super().__init__(request)
        self.thingy_id = request.match_info['thingy_id']
        try:
            self.timestamp = int(request.match_info['timestamp'])
        except KeyError:
            self.timestamp = None
        self.redis = request.app['redis']

    async def get(self):
        if self.timestamp is not None:
            val = await self.redis.zrevrangebyscore(self.thingy_id+':'+self.key, self.timestamp, self.timestamp)
            return json_response(body=val[0] if val else '{}')
        else:
            val = await self.redis.zrevrange(self.thingy_id+':'+self.key, 0, -1)
            return json_response(body='['+','.join(val)+']')

    async def put(self):
        data = await self.request.json()
        tr = self.redis.multi_exec()
        tr.zadd(self.thingy_id+':'+self.key, self.timestamp, dumps(data))
        tr.sadd('thingy', self.thingy_id)
        await tr.execute()
        return json_response(data)

class TemperatureView(SensorView):
    key = 'temperature'

class PressureView(SensorView):
    key = 'pressure'

class HumidityView(SensorView):
    key = 'humidity'

class GasView(SensorView):
    key = 'gas'

class ColorView(SensorView):
    key = 'color'

class ButtonView(View):
    states = {}

    def __init__(self, request):
        super().__init__(request)
        self.device_id = request.match_info['device_id']

    async def get(self):
        return json_response({'pressed': self.states[self.device_id]})

    async def put(self):
        state = await self.request.json()
        self.pressed[self.device_id] = state['pressed']
        return json_response(state)

async def button(request):
    pass

async def setup(request):
    settings = {
        'temperature': {'interval': 1000},
        'pressure': {'interval': 1000},
        'humidity': {'interval': 1000},
        'color': {'interval': 1000},
        'gas': {'mode': 1}
    }
    return json_response(settings)

class LEDCycle(object):

    def __init__(self):
        self.color_cycle = cycle(range(1,9))

    def __next__(self):
        return {
            'color': next(self.color_cycle),
            'intensity': 20,
            'delay': 1000
        }

led_cycle = LEDCycle()

async def led(request):
    if request.headers.get('EXPECT') == 'text/event-stream':
        async with sse_response(request) as resp:
            while True:
                await asyncio.sleep(1, loop=loop)
                resp.send(dumps(next(led_cycle)))
        return resp
    else:
        return json_response(next(led_cycle))

async def init(loop):
    app = web.Application(loop=loop)
    app['redis'] = await aioredis.create_redis(
            ('localhost', 6379), encoding='utf-8', loop=loop)

    app.router.add_get('/', devices)


    app.router.add_route('post', '/{thingy_id}/sensors/', sensors)
    app.router.add_route('*', '/{thingy_id}/sensors/{sensor:temperature|pressure|humidity|gas|color}', SensorView)
    app.router.add_route('*', '/{thingy_id}/temperature/{timestamp:\d+}', TemperatureView, name='temperature')
    app.router.add_route('*', '/{thingy_id}/pressure/{timestamp:\d+}', PressureView)
    app.router.add_route('*', '/{thingy_id}/humidity/{timestamp:\d+}', HumidityView)
    app.router.add_route('get', '/{thingy_id}/humidity/', HumidityView)
    app.router.add_route('*', '/{thingy_id}/gas/{timestamp:\d+}', GasView)
    app.router.add_route('*', '/{thingy_id}/color/{timestamp:\d+}', ColorView)
    app.router.add_route('*', '/{thingy_id}/button', button)

    app.router.add_get('/{device_id}/led', led)
    app.router.add_get('/{device_id}/setup', setup)

    srv = await loop.create_server(app.make_handler(), '127.0.0.1', 8080)
    return srv

loop.run_until_complete(init(loop))

try:
    loop.run_forever()
except KeyboardInterrupt:
    pass
