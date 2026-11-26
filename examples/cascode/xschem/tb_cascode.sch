v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
B 2 520 -420 1120 -120 {flags=graph
y1=-10
y2=30
ypos1=0
ypos2=2
divy=4
subdivy=1
unity=1
x1=0
x2=2e+11
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
node="\\"S21 (dB); s_2_1 db20()\\""
color=4
dataset=-1
unitx=G
logx=0
logy=0
}
B 2 520 -80 1120 220 {flags=graph
y1=-30
y2=0
ypos1=0
ypos2=2
divy=3
subdivy=1
unity=1
x1=0
x2=2e+11
divx=5
subdivx=1
xlabmag=1.0
ylabmag=1.0
node="\\"S11 (dB); s_1_1 db20()\\"
\\"S22 (dB); s_2_2 db20()\\""
color="7 12"
dataset=-1
unitx=G
logx=0
logy=0
}
T {Cascode with its EM model: bias and S-parameters} -520 -470 0 0 0.6 0.6 {}
T {x1 is the circuit from klayout_em_export, Create Circuit: the EM result of the layout
with the PDK transistors and resistors put back. Its pins have the layout's net names.} -520 -420 0 0 0.3 0.3 {}
T {bias tee} -230 -150 0 0 0.25 0.25 {layer=8}
T {bias tee} 170 -150 0 0 0.25 0.25 {layer=8}
T {port 1, 50 Ohm} -500 100 0 0 0.25 0.25 {layer=8}
T {port 2, 50 Ohm} 330 100 0 0 0.25 0.25 {layer=8}
N -110 -10 -200 -10 {lab=Cas_in}
N -200 -10 -240 -10 {lab=Cas_in}
N -200 -40 -200 -10 {lab=Cas_in}
N -300 -10 -420 -10 {lab=in}
N -420 -10 -420 20 {lab=in}
N 110 -10 200 -10 {lab=Cas_out}
N 200 -10 240 -10 {lab=Cas_out}
N 200 -40 200 -10 {lab=Cas_out}
N 300 -10 400 -10 {lab=out}
N 400 -10 400 20 {lab=out}
N -110 10 -150 10 {lab=Cas_Bias}
C {cascode_em_dc_ngspice.sym} 0 0 0 0 {name=x1}
C {devices/capa.sym} -270 -10 1 0 {name=Cin
m=1
value=10p}
C {devices/ind.sym} -200 -70 0 0 {name=Lb
m=1
value=1u}
C {devices/lab_pin.sym} -200 -100 1 0 {name=p1 sig_type=std_logic lab=vb}
C {devices/vsource.sym} -420 50 0 0 {name=Vin value="dc 0 ac 1 portnum 1 z0 50"}
C {devices/gnd.sym} -420 80 0 0 {name=l1 lab=GND}
C {devices/lab_pin.sym} -360 -10 1 0 {name=p2 sig_type=std_logic lab=in}
C {devices/capa.sym} 270 -10 1 0 {name=Cout
m=1
value=10p}
C {devices/ind.sym} 200 -70 0 0 {name=Lc
m=1
value=1u}
C {devices/lab_pin.sym} 200 -100 1 0 {name=p3 sig_type=std_logic lab=vcc}
C {devices/vsource.sym} 400 50 0 0 {name=Vout value="dc 0 ac 0 portnum 2 z0 50"}
C {devices/gnd.sym} 400 80 0 0 {name=l2 lab=GND}
C {devices/lab_pin.sym} 350 -10 1 0 {name=p4 sig_type=std_logic lab=out}
C {devices/lab_pin.sym} -150 10 0 0 {name=p5 sig_type=std_logic lab=Cas_Bias}
C {devices/lab_pin.sym} -150 -10 1 0 {name=p9 sig_type=std_logic lab=Cas_in}
C {devices/lab_pin.sym} 150 -10 1 0 {name=p10 sig_type=std_logic lab=Cas_out}
C {devices/vsource.sym} -480 250 0 0 {name=Vcc value=2.5}
C {devices/lab_pin.sym} -480 220 1 0 {name=p6 sig_type=std_logic lab=vcc}
C {devices/gnd.sym} -480 280 0 0 {name=l3 lab=GND}
C {devices/vsource.sym} -380 250 0 0 {name=Vb value=0.9}
C {devices/lab_pin.sym} -380 220 1 0 {name=p7 sig_type=std_logic lab=vb}
C {devices/gnd.sym} -380 280 0 0 {name=l4 lab=GND}
C {devices/vsource.sym} -280 250 0 0 {name=Vbias value=1.9}
C {devices/lab_pin.sym} -280 220 1 0 {name=p8 sig_type=std_logic lab=Cas_Bias}
C {devices/gnd.sym} -280 280 0 0 {name=l5 lab=GND}
C {devices/code_shown.sym} -520 340 0 0 {name=MODEL only_toplevel=true
format="tcleval( @value )"
value="
.lib $::SG13G2_MODELS/cornerHBT.lib hbt_typ
"}
C {devices/code_shown.sym} -160 170 0 0 {name=NGSPICE only_toplevel=true
value="
.control
op
print -i(Vcc) -i(Vbias)
sp lin 200 1g 200g
let s21db = db(S_2_1)
meas sp s21_10g find s21db at=10g
meas sp s21_100g find s21db at=100g
write tb_cascode.raw
.endc
"}
C {devices/launcher.sym} 580 -450 0 0 {name=h1
descr="load the results"
tclcommand="xschem raw_read $netlist_dir/tb_cascode.raw sp"
}
