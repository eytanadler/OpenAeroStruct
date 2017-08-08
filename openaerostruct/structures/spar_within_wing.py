from __future__ import print_function, division
import numpy as np

from openmdao.api import ExplicitComponent
from openaerostruct.structures.utils import radii

try:
    from openaerostruct.fortran import OAS_API
    fortran_flag = True
    data_type = float
except:
    fortran_flag = False
    data_type = complex

class SparWithinWing(ExplicitComponent):
    """
    Create a constraint to see if the spar is within the wing.
    This is based on the wing's t/c and the spar radius.

    .. warning::
        This component has not been extensively tested.
        It may require additional coding to work as intended.

    inputeters
    ----------
    mesh[nx, ny, 3] : numpy array
        Array defining the nodal points of the lifting surface.
    radius[ny-1] : numpy array
        Radius of each element of the FEM spar.

    Returns
    -------
    spar_within_wing[ny-1] : numpy array
        If all the values are negative, each element is within the wing,
        based on the surface's t_over_c value and the current chord.
        Set a constraint with
        `OASProblem.add_constraint('spar_within_wing', upper=0.)`
    """

    def initialize(self):
        self.metadata.declare('surface', type_=dict)

    def setup(self):
        self.surface = surface = self.metadata['surface']

        self.ny = surface['num_y']
        nx = surface['num_x']

        self.add_input('mesh', val=np.random.random_sample((nx, self.ny, 3)), units='m')
        self.add_input('radius', val=np.random.random_sample((self.ny-1)), units='m')
        self.add_output('spar_within_wing', val=np.zeros((self.ny-1)), units='m')


        self.approx_partials('*', '*')

    def compute(self, inputs, outputs):
        mesh = inputs['mesh']
        max_radius = radii(mesh, self.surface['t_over_c'])
        outputs['spar_within_wing'] = inputs['radius'] - max_radius

    def compute_partials(self, inputs, partials):
        partials['spar_within_wing', 'radius'] = np.eye(self.ny-1)
