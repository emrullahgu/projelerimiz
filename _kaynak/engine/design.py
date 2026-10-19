"""CLD engine - runs every discipline for one parcel."""
from model import Building
from mech import MechDesign
from plumb import PlumbDesign
from elec import ElecDesign
from earth import EarthDesign


class Project:
    def __init__(self, parcel, dump, log=print):
        self.parcel = str(parcel)
        self.b = Building(self.parcel, dump, log=log)
        self.mech = MechDesign(self.b)
        self.plumb = PlumbDesign(self.b)
        mech_kw = self.mech.sum['kw'] + self.plumb.sum['hyd_kw']   # standby pump not in demand
        fire_kw = self.plumb.sum['fire_kw'] + self.plumb.sum['jockey_kw']
        self.elec = ElecDesign(self.b, mech_kW=mech_kw, fire_kW=fire_kw, mech=self.mech, plumb=self.plumb)
        self.earth = EarthDesign(self.b, self.elec, self.mech)
