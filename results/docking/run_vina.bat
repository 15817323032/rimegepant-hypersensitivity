@echo off
cd /d %~dp0

vina --config vina_CALCRL.txt --out CALCRL_out.pdbqt --log CALCRL.log
vina --config vina_RAMP1.txt --out RAMP1_out.pdbqt --log RAMP1.log
vina --config vina_SYK.txt --out SYK_out.pdbqt --log SYK.log
vina --config vina_BTK.txt --out BTK_out.pdbqt --log BTK.log
