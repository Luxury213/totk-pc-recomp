"""Verify client endpoint isolation and deliberate loss in the UDP test bridge, without ENet or a game."""
import socket
import unittest

from coop_network_check import ImpairedLink


class ProxyChecks(unittest.TestCase):
    def endpoint(self):
        endpoint = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        endpoint.bind(('127.0.0.1', 0))
        endpoint.settimeout(2)
        self.addCleanup(endpoint.close)
        return endpoint

    def test_later_client_cannot_receive_an_earlier_clients_reply(self):
        server, first, second = self.endpoint(), self.endpoint(), self.endpoint()
        bridge = ImpairedLink(server.getsockname()[1], 20, impair=False)
        self.addCleanup(bridge.close)
        address = ('127.0.0.1', bridge.port)
        first.sendto(b'first request', address)
        request, first_route = server.recvfrom(100)
        self.assertEqual(request, b'first request')
        second.sendto(b'second request', address)
        request, second_route = server.recvfrom(100)
        self.assertEqual(request, b'second request')
        # Reply after both clients have sent: the server must still be able to address each one.
        server.sendto(b'first reply', first_route)
        server.sendto(b'second reply', second_route)
        self.assertEqual(first.recvfrom(100)[0], b'first reply')
        self.assertEqual(second.recvfrom(100)[0], b'second reply')
        self.assertNotEqual(first_route, second_route)

    def test_forced_loss_drops_only_one_server_disconnect(self):
        server, client = self.endpoint(), self.endpoint()
        bridge = ImpairedLink(server.getsockname()[1], 0, impair=False, drop_first_disconnect=True)
        self.addCleanup(bridge.close)
        client.sendto(b'route request', ('127.0.0.1', bridge.port))
        _, route = server.recvfrom(100)
        # Authored ENet control fixture: timestamped header, acknowledged DISCONNECT, reason two.
        disconnect = bytes.fromhex('8000000084ff000100000002')
        server.sendto(disconnect, route)
        server.sendto(b'after loss', route)
        self.assertEqual(client.recvfrom(100)[0], b'after loss')
        server.sendto(disconnect, route)
        self.assertEqual(client.recvfrom(100)[0], disconnect)
        self.assertEqual(bridge.counts['forced_disconnect_drops'], 1)


if __name__ == '__main__':
    unittest.main()
