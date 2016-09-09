import numpy as np

import vispy.scene.cameras as viscam

from ...utils import slider2opacity

__all__ = ['uiOpacity']

class uiOpacity(object):

    """ui for atlas
    """
    
    def __init__(self,):
        # --------------- MNI ---------------
        # Opacity :
        self.OpacitySlider.sliderMoved.connect(self.fcn_opacity)
        self._slmin = self.OpacitySlider.minimum()
        self._slmax = self.OpacitySlider.maximum()
        # Fixed rotation :
        self.q_coronal.clicked.connect(self.fcn_coronal)
        self.q_axial.clicked.connect(self.fcn_axial)
        self.q_sagittal.clicked.connect(self.fcn_sagittal)
        # Cameras types :
        self.c_Turnable.clicked.connect(self.fcn_switch_camera)
        self.c_Arcball.clicked.connect(self.fcn_switch_camera)
        self.c_Magnify.clicked.connect(self.fcn_switch_camera)
        self.c_Fly.clicked.connect(self.fcn_switch_camera)
        # Slice :
        # Set maximum and minimum for each slice :
        minfact = 1.2
        self.xSlices.setMinimum(self.atlas.vert[:, 0].min()*minfact)
        self.xSlices.setMaximum(self.atlas.vert[:, 0].max()*minfact)
        self.ySlices.setMinimum(self.atlas.vert[:, 1].min()*minfact)
        self.ySlices.setMaximum(self.atlas.vert[:, 1].max()*minfact)
        self.zSlices.setMinimum(self.atlas.vert[:, 2].min()*minfact)
        self.zSlices.setMaximum(self.atlas.vert[:, 2].max()*minfact)
        self.xSlices.sliderMoved.connect(self.fcn_xyzSlice)
        self.ySlices.sliderMoved.connect(self.fcn_xyzSlice)
        self.zSlices.sliderMoved.connect(self.fcn_xyzSlice)

    def _getOpacitySlider(self, tomin=0, tomax=1):
        """
        """
        sl = self.OpacitySlider.value()
        slval = slider2opacity(sl, thmin=0.0, thmax=100.0, vmin=self._slmin, vmax=self._slmax,
                               tomin=tomin, tomax=tomax)
        return slval, sl

    def fcn_opacity(self):
        """Change opacity using the slider
        """
        # Get slider value :
        slval, sl = self._getOpacitySlider(tomin=self.view.minOpacity, tomax=self.view.maxOpacity)

        # Brain opacity :
        # Get vertices and color :
        if self.o_Brain.isChecked():
            vcolor = self.atlas.mesh.mesh_data.get_vertex_colors()
            # Apply either on all objects or only visible objects :
            vcolor[~self.atlas.mask, 3] = slval
            self.atlas.mesh.mesh_data.set_vertex_colors(vcolor)
            self.atlas.mesh.mesh_data_changed()

        # Sources opacity :
        if self.o_Sources.isChecked():
            sl_01 = (sl-self._slmin)/(self._slmax-self._slmin)
            self.sources.sColor[:, 3] = sl_01
            self.sources.edgecolor[:, 3] = sl_01
            self.sources.update()

        # Text opacity :
        if self.o_Text.isChecked():
            sl_01 = (sl-self._slmin)/(self._slmax-self._slmin)
            self.sources.stextcolor[:, 3] = sl_01
            self.sources.stextmesh.opacity = sl_01
            self.sources.text_update()


    # def _brain_opacity(self)

    def fcn_coronal(self):
        """Fixed coronal view
        """
        self.rotate_fixed(vtype='coronal')


    def fcn_axial(self):
        """Fixed axial view
        """
        self.rotate_fixed(vtype='axial')


    def fcn_sagittal(self):
        """Fixed coronal view
        """
        self.rotate_fixed(vtype='sagittal')


    def fcn_switch_camera(self):
        """Switch between diffrent types of cameras
        """
        # Get radio buttons values :
        if self.c_Turnable.isChecked():
            self.view.wc.camera = viscam.TurntableCamera(elevation=90, distance=10.0,
                                                                fov=0, azimuth=0)
        if self.c_Arcball.isChecked():
            self.view.wc.camera = viscam.ArcballCamera()
        if self.c_Magnify.isChecked():
            self.view.wc.camera = viscam.MagnifyCamera()
        if self.c_Fly.isChecked():
            self.view.wc.camera = viscam.FlyCamera()


    def fcn_xyzSlice(self):
        """Define x, y and z slices of the brain
        """
        # Get checkbox position :
        xsym = '<' if self.xInvert.isChecked() else '>'
        ysym = '<' if self.yInvert.isChecked() else '>'
        zsym = '<' if self.zInvert.isChecked() else '>'

        # Get slide positions :
        xsl, ysl, zsl = self.xSlices.value(), self.ySlices.value(), self.zSlices.value()

        # Define a default string for all objects :
        formatstr = 'np.array(({obj}[:, 0] {xsym} xsl) | ({obj}[:, 1] {ysym} ysl) | ({obj}[:, 2] {zsym} zsl))'

        # Slice brain :
        if self.o_Brain.isChecked():
            # Reset mask :
            self.atlas.mask = np.zeros_like(self.atlas.mask)
            # Find vertices to remove :
            tohide = eval(formatstr.format(obj='self.atlas.vert', xsym=xsym, ysym=ysym, zsym=zsym))
            # Update mask :
            self.atlas.mask[tohide] = True
            # Get vertices and color :
            vcolor = self.atlas.mesh.mesh_data.get_vertex_colors()
            # Update opacity for non-hide vertices :
            vcolor[self.atlas.mask, 3] = self.view.minOpacity
            vcolor[~self.atlas.mask, 3] = self._getOpacitySlider(tomin=self.view.minOpacity, tomax=self.view.maxOpacity)[0]
            self.atlas.mesh.mesh_data.set_vertex_colors(vcolor)
            self.atlas.mesh.mesh_data_changed()     

        # Sources opacity :
        if self.o_Sources.isChecked() or self.o_Text.isChecked():
            # Reset mask :
            self.sources.data.mask = np.zeros_like(self.sources.data.mask)
            # Find sources to remove :
            tohide = eval(formatstr.format(obj='self.sources.xyz', xsym=xsym, ysym=ysym, zsym=zsym))
            # Update mask then sources :
            self.sources.data.mask[tohide] = True
            if self.o_Sources.isChecked(): self.sources.update()
            if self.o_Text.isChecked(): self.sources.text_update()
