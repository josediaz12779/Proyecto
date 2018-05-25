# Copyright 2011-2012 James McCauley
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
l2 learning switch modificado del codigo original de James McCauley
Este es el esqueleto que usaremos para construir nuestras aplicaciones
note que este codigo tiene una funcion nueva llamada bloquear_paquete
Note el momento en que la funcion es invocada, es alli donde realizaremos las acciones que requiera el proyecto final,
cada grupo debe crear una funcion que realice la funcion correspondiente a su proyecto


"""

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpid_to_str
from pox.lib.util import str_to_bool
#import pox.lib.packet.ethernet as pkt
import pox.lib.packet as pkt
from pox.lib.addresses import IPAddr, EthAddr
import time

log = core.getLogger()
ICMP = pkt.ipv4.ICMP_PROTOCOL
TCP = pkt.ipv4.TCP_PROTOCOL
UDP = pkt.ipv4.UDP_PROTOCOL
#ip_para_bloquear = "10.0.0.1"


# We don't want to flood immediately when a switch connects.
# Can be overriden on commandline.
_flood_delay = 0

class LearningSwitch (object):
  """
  The learning switch "brain" associated with a single OpenFlow switch.

  When we see a packet, we'd like to output it on a port which will
  eventually lead to the destination.  To accomplish this, we build a
  table that maps addresses to ports.

  We populate the table by observing traffic.  When we see a packet
  from some source coming from some port, we know that source is out
  that port.

  When we want to forward traffic, we look up the desintation in our
  table.  If we don't know the port, we simply send the message out
  all ports except the one it came in on.  (In the presence of loops,
  this is bad!).

  In short, our algorithm looks like this:

  For each packet from the switch:
  1) Use source address and switch port to update address/port table
  2) Is transparent = False and either Ethertype is LLDP or the packet's
     destination address is a Bridge Filtered address?
     Yes:
        2a) Drop packet -- don't forward link-local traffic (LLDP, 802.1x)
            DONE
  3) Is destination multicast?
     Yes:
        3a) Flood the packet
            DONE
  4) Port for destination address in our address/port table?
     No:
        4a) Flood the packet
            DONE
  5) Is output port the same as input port?
     Yes:
        5a) Drop packet and similar ones for a while
  6) Install flow table entry in the switch so that this
     flow goes out the appopriate port
     6a) Send the packet out appropriate port
  """
  def __init__ (self, connection, transparent):
    # Switch we'll be adding L2 learning switch capabilities to
    self.connection = connection
    self.transparent = transparent

    # Our table
    self.macToPort = {}

    # We want to hear PacketIn messages, so we listen
    # to the connection
    connection.addListeners(self)

    # We just use this to know when to log a helpful message
    self.hold_down_expired = _flood_delay == 0

    #log.debug("Initializing LearningSwitch, transparent=%s",
    #          str(self.transparent))

 # def mostrar_paquete(self, event):
 #	packet = event.parsed
 #       ip_packet = packet.payload
 #       payload2 = ip_packet.payload
 #	payload3 = payload2.payload
 #       print "payload paquete ", payload2
 #	print "payload paquete 3 ", payload3  

  def bloquear_paquete(self, event):

    # Recuerde que crearemos el match a partir del paquete
    packet = event.parsed
    print "Mensaje bloqueado"

    # Este mensaje de tipo "flow_mod" modifica la tabla de flujos del switch
    msg = of.ofp_flow_mod()
    # Creamos el match de la entrada en la tabla de flujos a partir del paquete
    msg.match = of.ofp_match.from_packet(packet, event.port)

    # Recuerde que para hacer DROP de un paquete, basta con crear una regla sin accion (examine con la regla creada mas abajo y verificara que la otra si tiene un action)
    msg.idle_timeout = 10
    msg.hard_timeout = 30
    msg.data = event.ofp # 6a
    self.connection.send(msg)
    #def handle_IP_packet (packet):
    #ip = packet.find('ipv4')
    #if ip is None:
    #return
    #print "Source IP: ", ip.srcip	


  def _handle_PacketIn (self, event):
    """
    Handle packet in messages from the switch to implement above algorithm.
    """

    packet = event.parsed

    def flood (message = None):
      """ Floods the packet """
      msg = of.ofp_packet_out()
      if time.time() - self.connection.connect_time >= _flood_delay:
        # Only flood if we've been connected for a little while...

        if self.hold_down_expired is False:
          # Oh yes it is!
          self.hold_down_expired = True
          log.info("%s: Flood hold-down expired -- flooding",
              dpid_to_str(event.dpid))

        if message is not None: log.debug(message)
        #log.debug("%i: flood %s -> %s", event.dpid,packet.src,packet.dst)
        # OFPP_FLOOD is optional; on some switches you may need to change
        # this to OFPP_ALL.
        msg.actions.append(of.ofp_action_output(port = of.OFPP_FLOOD))
      else:
        pass
        #log.info("Holding down flood for %s", dpid_to_str(event.dpid))
      msg.data = event.ofp
      msg.in_port = event.port
      self.connection.send(msg)

    def drop (duration = None):
      """
      Drops this packet and optionally installs a flow to continue
      dropping similar ones for a while
      """
      if duration is not None:
        if not isinstance(duration, tuple):
          duration = (duration,duration)
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet)
        msg.idle_timeout = duration[0]
        msg.hard_timeout = duration[1]
        msg.buffer_id = event.ofp.buffer_id
        self.connection.send(msg)
      elif event.ofp.buffer_id is not None:
        msg = of.ofp_packet_out()
        msg.buffer_id = event.ofp.buffer_id
        msg.in_port = event.port
        self.connection.send(msg)

    self.macToPort[packet.src] = event.port # 1

    if not self.transparent: # 2
      if packet.type == packet.LLDP_TYPE or packet.dst.isBridgeFiltered():
        drop() # 2a
        return

    # Este es el lugar apropiado para ingresar nuestra funcion personalizada, porque ya se realizaron los chequeos que le permiten a l2 enrutar paquetes
    # Note el siguiente if, es imporante porque en este evento llegan TODOS los paquetes que pasen por la red (incluyendo paquetes ARP que no son IP)
    # Por esta razon, solo aplicamos reglas a los paquetes IP 
    # Nota: Este if no aplicaria para el proyecto que tiene el proyecto "arp defense" por obvias razones
   
    if packet.type == pkt.ethernet.IP_TYPE:   
        # El evento packet_in recibe un objeto llamado "evento", este evento contiene informacion importante
        # 1. El puerto por el que ingresa el paquete, que es necesario para realizar el enrutamiento
        # 2. El paquete que produjo el evento, lo que hace este codigo es parsear ese paquete, es decir, obtener los encabezados necesarios del paquete para identificar
        #    si debe o no bloquear el flujo 
        ip_packet = packet.payload
        if ip_packet.protocol == ICMP:
	  icmp_packet = ip_packet.payload
          # El paquete que recibimos es de tipo "Ethernet", asi que su carga util sera un paquete IP (revisar modelo OSI)
          # El paquete ip_packet ya es un paquete IP, por lo tal posee un campo que es "direccion IP de origen" srcip
          ip_origen = ip_packet.srcip
	  ip_destino = ip_packet.dstip		
	  #icmp_code = icmp_packet.code
          print "IP Origen: ", ip_origen
	  print "IP Destino: ", ip_destino
	  #print "Codigo ICMP: ", icmp_code
          # Note la funcion IPAddr, se usa para manejar direcciones IP, en este caso le entregamos un string y nos devuelve un objeto de tipo direccion IP
          #if (ip_origen == IPAddr(ip_para_bloquear)): 
          # Si el paquete que genero este evento coincide con nuestra condicion, invocamos la funcion de bloquear
          self.bloquear_paquete(event)
          return

        if ip_packet.protocol == TCP:
	  tcp_packet = ip_packet.payload
	  ip_origen = ip_packet.srcip
	  ip_destino = ip_packet.dstip
	  print "IP Origen: ", ip_origen
	  print "IP Destino: ", ip_destino
	  print "La prueba es de tipo TCP"
	  self.bloquear_paquete(event)
	  return

	if ip_packet.protocol == UDP:
	  udp_packet = ip_packet.payload
	  ip_origen = ip_packet.srcip
	  ip_destino = ip_packet.dstip
	  print "IP Origen: ", ip_origen
	  print "IP Destino: ", ip_destino
	  print "La prueba es de tipo UDP"
	  self.bloquear_paquete(event)
          return   

    if packet.dst.is_multicast:
      flood() # 3a
    else:
      if packet.dst not in self.macToPort: # 4
        flood("Port for %s unknown -- flooding" % (packet.dst,)) # 4a
      else:
        port = self.macToPort[packet.dst]
        if port == event.port: # 5
          # 5a
          log.warning("Same port for packet from %s -> %s on %s.%s.  Drop."
              % (packet.src, packet.dst, dpid_to_str(event.dpid), port))
          drop(10)
          return
        # 6
        log.debug("installing flow for %s.%i -> %s.%i" %
                  (packet.src, event.port, packet.dst, port))
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match.from_packet(packet, event.port)
        msg.idle_timeout = 10
        msg.hard_timeout = 30
        msg.actions.append(of.ofp_action_output(port = port))
        msg.data = event.ofp # 6a
        self.connection.send(msg)


class l2_learning (object):
  """
  Waits for OpenFlow switches to connect and makes them learning switches.
  """
  def __init__ (self, transparent):
    core.openflow.addListeners(self)
    self.transparent = transparent

  def _handle_ConnectionUp (self, event):
    log.debug("Connection %s" % (event.connection,))
    LearningSwitch(event.connection, self.transparent)


def launch (transparent=False, hold_down=_flood_delay):
  """
  Starts an L2 learning switch.
  """
  try:
    global _flood_delay
    _flood_delay = int(str(hold_down), 10)
    assert _flood_delay >= 0
  except:
    raise RuntimeError("Expected hold-down to be a number")

  core.registerNew(l2_learning, str_to_bool(transparent))
  core.openflow.miss_send_len = 0x7fff
