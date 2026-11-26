v {xschem version=3.4.5 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {The EM model with the PDK devices, from klayout_em_export (Create Circuit)} -300 -260 0 0 0.4 0.4 {}
T {Add your sources and loads at the pins, and your analysis to the commands below.} -300 -220 0 0 0.3 0.3 {}
C {cascode_em_dc_ngspice.sym} 0 0 0 0 {name=x1}
C {devices/lab_pin.sym} 110 -10 0 1 {name=p1 sig_type=std_logic lab=Cas_out}
C {devices/lab_pin.sym} -110 -10 0 0 {name=p2 sig_type=std_logic lab=Cas_in}
C {devices/lab_pin.sym} -110 10 0 0 {name=p3 sig_type=std_logic lab=Cas_Bias}
C {devices/code_shown.sym} -300 160 0 0 {name=MODEL only_toplevel=true
format="tcleval( @value )"
value="
.lib $::SG13G2_MODELS/cornerHBT.lib hbt_typ
"}
C {devices/code_shown.sym} 200 160 0 0 {name=NGSPICE only_toplevel=true
value="
.control
op
print v(Cas_out) v(Cas_in) v(Cas_Bias)
.endc
"}
