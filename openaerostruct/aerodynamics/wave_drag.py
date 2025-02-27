import numpy as np

import openmdao.api as om


class WaveDrag(om.ExplicitComponent):
    """
    Compute the wave drag if the with_wave option is True. If not, the CDw is 0.
    This component exists for each lifting surface.

    Parameters
    ----------
    Mach_number : float
        Mach number.
    widths[ny-1] : numpy array
        The width in the spanwise direction of each VLM panel. This is the numerator of cos(sweep).
    lengths_spanwise[ny-1] : numpy array
        The spanwise length of each VLM panel at 1/4 chord, rotated by the sweep angle. This is the denominator
        of cos(sweep)
    CL : float
        The CL of the lifting surface used for wave drag estimation.
    chords[ny] : numpy array
        The chord length of each mesh slice. This is dimension ny rather than ny-1 which would be
        expected for chord length of each VLM panel.
    t_over_c[ny-1] : numpy array
        The streamwise thickness-to-chord ratio of each VLM panel.

    Returns
    -------
    CDw : float
        Wave drag coefficient for the lifting surface computed using equations based on the
        Korn equation
    """

    def initialize(self):
        self.options.declare("surface", types=dict)
        self.options.declare("with_wave", types=bool)

    def setup(self):
        self.surface = surface = self.options["surface"]
        self.with_wave = surface["with_wave"]

        # Thickness over chord for the airfoil
        self.ka = 0.95  # airfoil technology level (for NASA SC airfoil)

        ny = surface["mesh"].shape[1]

        self.add_input("Mach_number", val=1.6)
        self.add_input("widths", val=np.ones((ny - 1)) * 0.2, units="m")
        self.add_input(
            "lengths_spanwise", val=np.arange((ny - 1)) + 1.0, units="m"
        )  # set to np.arange so that d_CDw_d_chords is nonzero
        self.add_input("CL", val=0.33)
        self.add_input("chords", val=np.ones((ny)), units="m")
        self.add_input("t_over_c", val=np.arange((ny - 1)))
        self.add_output("CDw", val=0.0)

        self.declare_partials("CDw", "*")
        self.set_check_partial_options(wrt="*", method="cs", step=1e-50)

    def compute(self, inputs, outputs):
        if self.with_wave:
            t_over_c = inputs["t_over_c"]
            widths = inputs["widths"]
            cos_sweep = widths / inputs["lengths_spanwise"]
            M = inputs["Mach_number"]
            chords = inputs["chords"]
            CL = inputs["CL"]

            mean_chords = (chords[:-1] + chords[1:]) / 2.0
            panel_areas = mean_chords * widths
            avg_cos_sweep = np.sum(cos_sweep * panel_areas) / np.sum(panel_areas)  # weighted average of 1/4 chord sweep
            avg_t_over_c = np.sum(t_over_c * panel_areas) / np.sum(panel_areas)  # weighted average of streamwise t/c
            MDD = self.ka / avg_cos_sweep - avg_t_over_c / avg_cos_sweep**2 - CL / (10 * avg_cos_sweep**3)
            Mcrit = MDD - (0.1 / 80.0) ** (1.0 / 3.0)

            if M > Mcrit:
                outputs["CDw"] = 20 * (M - Mcrit) ** 4
            else:
                outputs["CDw"] = 0.0

            if self.surface["symmetry"]:
                outputs["CDw"] *= 2
        else:
            outputs["CDw"] = 0.0

    def compute_partials(self, inputs, partials):
        """Jacobian for wave drag."""
        if self.with_wave:
            ny = self.surface["mesh"].shape[1]
            t_over_c = inputs["t_over_c"]
            widths = inputs["widths"]
            lengths_spanwise = inputs["lengths_spanwise"]
            cos_sweep = widths / lengths_spanwise
            M = inputs["Mach_number"]
            chords = inputs["chords"]
            CL = inputs["CL"]

            chords = (chords[:-1] + chords[1:]) / 2.0
            panel_areas = chords * widths
            sum_panel_areas = np.sum(panel_areas)
            avg_cos_sweep = np.sum(cos_sweep * panel_areas) / sum_panel_areas
            avg_t_over_c = np.sum(t_over_c * panel_areas) / sum_panel_areas

            MDD = 0.95 / avg_cos_sweep - avg_t_over_c / avg_cos_sweep**2 - CL / (10 * avg_cos_sweep**3)
            Mcrit = MDD - (0.1 / 80.0) ** (1.0 / 3.0)

            if M > Mcrit:
                dCDwdMDD = -80 * (M - Mcrit) ** 3
                dMDDdCL = -1.0 / (10 * avg_cos_sweep**3)
                dMDDdavg = (-10 * self.ka * avg_cos_sweep**2 + 20 * avg_t_over_c * avg_cos_sweep + 3 * CL) / (
                    10 * avg_cos_sweep**4
                )
                dMDDdtoc = -1.0 / (avg_cos_sweep**2)
                dtocavgdtoc = panel_areas / sum_panel_areas

                ccos = np.sum(widths * chords)
                ccos2w = np.sum(chords * widths**2 / lengths_spanwise)

                davgdcos = 2 * chords * widths / lengths_spanwise / ccos - chords * ccos2w / ccos**2
                dtocdcos = chords * t_over_c / ccos - chords * np.sum(chords * widths * t_over_c) / ccos**2
                davgdw = -1 * chords * widths**2 / lengths_spanwise**2 / ccos
                davgdc = widths**2 / lengths_spanwise / ccos - widths * ccos2w / ccos**2
                dtocdc = t_over_c * widths / ccos - widths * np.sum(chords * widths * t_over_c) / ccos**2

                dcdchords = np.zeros((ny - 1, ny))
                i, j = np.indices(dcdchords.shape)
                dcdchords[i == j] = 0.5
                dcdchords[i == j - 1] = 0.5

                partials["CDw", "Mach_number"] = -1 * dCDwdMDD
                partials["CDw", "CL"] = dCDwdMDD * dMDDdCL
                partials["CDw", "lengths_spanwise"] = dCDwdMDD * dMDDdavg * davgdw
                partials["CDw", "widths"] = dCDwdMDD * dMDDdavg * davgdcos + dCDwdMDD * dMDDdtoc * dtocdcos
                partials["CDw", "chords"] = dCDwdMDD * dMDDdavg * np.matmul(
                    davgdc, dcdchords
                ) + dCDwdMDD * dMDDdtoc * np.matmul(dtocdc, dcdchords)
                partials["CDw", "t_over_c"] = dCDwdMDD * dMDDdtoc * dtocavgdtoc

        if self.surface["symmetry"]:
            partials["CDw", "CL"][0, :] *= 2
            partials["CDw", "lengths_spanwise"][0, :] *= 2
            partials["CDw", "widths"][0, :] *= 2
            partials["CDw", "Mach_number"][0, :] *= 2
            partials["CDw", "chords"][0, :] *= 2
            partials["CDw", "t_over_c"][0, :] *= 2
