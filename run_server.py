import asyncio
from aiohttp import web
from aiohttp.web import Application, Response, json_response, HTTPNotAcceptable, View
from aiohttp_sse import sse_response

from json import dumps
from collections import defaultdict
from itertools import cycle


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
        loop = request.app.loop
        async with sse_response(request) as resp:
            while True:
                await asyncio.sleep(1, loop=loop)
                resp.send(dumps(next(led_cycle)))
        return resp
    else:
        return json_response(next(led_cycle))

class SensorView(View):
    data = defaultdict(lambda : defaultdict(int))

    def __init__(self, request):
        super().__init__(request)
        self.device_id = request.match_info['device_id']
        self.timestamp = request.match_info['timestamp']

    async def get(self):
        return json_response({'value': self.data[self.device_id][self.timestamp]})

    async def put(self):
        sensor = await self.request.json()
        self.data[self.device_id][self.timestamp] = sensor['value']
        return json_response({'value': sensor['value']})

class TemperatureView(SensorView):
    pass

class PressureView(SensorView):
    pass

class HumidityView(SensorView):
    pass

class GasView(SensorView):
    pass

class ColorView(SensorView):
    pass

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

app = web.Application()

app.router.add_route('*', '/{device_id}/temperature/{timestamp}', TemperatureView)
app.router.add_route('*', '/{device_id}/pressure/{timestamp}', PressureView)
app.router.add_route('*', '/{device_id}/humidity/{timestamp}', HumidityView)
app.router.add_route('*', '/{device_id}/gas/{timestamp}', GasView)
app.router.add_route('*', '/{device_id}/color/{timestamp}', ColorView)
app.router.add_route('*', '/{device_id}/button', button)

app.router.add_get('/{device_id}/led', led)
app.router.add_get('/{device_id}/setup', setup)

web.run_app(app, host='127.0.0.1', port=8080)
