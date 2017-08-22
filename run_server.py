import asyncio
from aiohttp import web
from aiohttp.web import Application, Response, json_response, HTTPNotAcceptable
from aiohttp_sse import sse_response

from json import dumps
from collections import defaultdict
from itertools import cycle
from logging import getLogger

logger = getLogger(__name__)


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

class AcceptChooser:

    def __init__(self):
        self._accepts = {}

    async def do_route(self, request):
        for accept in request.headers.getall('ACCEPT', []):
            acceptor = self._accepts.get(accept)
            if acceptor is not None:
                return (await acceptor(request))
        raise HTTPNotAcceptable()

    def reg_acceptor(self, accept, handler):
        self._accepts[accept] = handler


device_data = {}

#async def led(request):
#    if request.headers.get('EXPECT') == 'text/event-stream':
#        raise HTTPExpectationFailed(text="Unknown Expect: %s" % expect)

async def led_stream(request):
    loop = request.app.loop
    async with sse_response(request) as resp:
        while True:
            await asyncio.sleep(1, loop=loop)
            resp.send(dumps(next(led_cycle)))
    return resp

async def led_json(request):
    return json_response(next(led_cycle))


class View:
    def __init__(self, request):
        self.request = request

    @classmethod
    async def dispatch(cls, request):
        view = cls(request)
        method = getattr(view, request.method.lower())
        logger.info("Serving %s %s", request.method, request.path)

        if not method:
            return HTTPMethodNotAllowed()

        return await method()

    async def options(self):
        return Response()

class SensorView(View):
    data = defaultdict(lambda : defaultdict(int))

    def __init__(self, request):
        super().__init__(request)
        self.device_id = request.match_info['device_id']
        self.timestamp = request.match_info['timestamp']

    async def get(self):
        return json_response(self.data[self.device_id][self.timestamp])

    async def put(self):
        sensor = await self.request.json()
        self.data[self.device_id][self.timestamp] = sensor['value']
        return json_response({'hello': 'world'})

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

class ButtonView():

    states = {}

    def __init__(self, request):
        super().__init__(request)
        self.device_id = request.match_info['device_id']

    async def get(self):
        return json_response(self.states[self.device_id])

    async def put(self):
        state = await self.request.json()
        self.pressed[self.device_id] = state
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

app.router.add_route('*', '/{device_id}/temperature/{timestamp}', TemperatureView.dispatch)
app.router.add_route('*', '/{device_id}/pressure/{timestamp}', PressureView.dispatch)
app.router.add_route('*', '/{device_id}/humidity/{timestamp}', HumidityView.dispatch)
app.router.add_route('*', '/{device_id}/gas/{timestamp}', GasView.dispatch)
app.router.add_route('*', '/{device_id}/color/{timestamp}', ColorView.dispatch)
app.router.add_route('*', '/{device_id}/button', ButtonView.dispatch)

chooser = AcceptChooser()
app.router.add_get('/{device_id}/led', chooser.do_route)
chooser.reg_acceptor('text/event-stream', led_stream)
chooser.reg_acceptor('application/json', led_json)

app.router.add_get('/{device_id}/setup', setup)

web.run_app(app, host='127.0.0.1', port=8080)
