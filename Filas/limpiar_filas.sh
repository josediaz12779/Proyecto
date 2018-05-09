#!/bin/bash

#Este script borra las filas y los registros de QoS creados en las interfaces del switch
set -e

bridges="$(ovs-vsctl show | grep Port | awk '{print $2}' |  sudo ovs-vsctl show | grep Port | awk '{print $2}' | sed -e 's/^"//' -e 's/"$//')"
# | cut -c 2-3)"
echo $bridges

for i in $bridges; do
	echo $i
	ovs-vsctl -- clear Port $i qos
done

ovs-vsctl -- --all destroy QoS
ovs-vsctl -- --all destroy Queue
