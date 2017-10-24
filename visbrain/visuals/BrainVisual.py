"""Create and control a 3D object.

This class can be used to create a 3D object, based on vertices and faces. It
can be used to create the main brain or areas (like brodmann / gyrus). This
class is also responsible of turning camera rotations into light ajustement.

This class inherit from vispy.visuals so it can be turned into a vispy node,
which make it easier to add vispy transformations.

Authors: Etienne Combrisson <e.combrisson@gmail.com>

License: BSD (3-clause)
"""
import numpy as np

from vispy import gloo
from vispy.visuals import Visual
import vispy.visuals.transforms as vist
from vispy.scene.visuals import create_visual_node

from ..utils import (array2colormap, color2vb, convert_meshdata, vispy_array,
                     wrap_properties)


# Vertex shader : executed code for individual vertices. The transformation
# applied to each one of them is the camera rotation.
VERT_SHADER = """
#version 120
varying vec3 v_position;
varying vec4 v_color;
varying vec3 v_normal;

void main() {
    v_position = $a_position;
    v_normal = $a_normal;
    v_color = $a_color * $u_light_color;
    gl_Position = $transform(vec4($a_position, 1));
}
"""


# Fragment shader : executed code to each Fragment generated by the
# Rasterization and turn it into a set of colors and a single depth value.
# The code bellow generate three types of light :
# * Ambient : uniform light across fragments
# * Diffuse : ajust light according to normal vector
# * Specular : add some high-density light for a "pop / shiny" effect.
FRAG_SHADER = """
#version 120
varying vec3 v_position;
varying vec4 v_color;
varying vec3 v_normal;

void main() {

    // ----------------- Ambient light -----------------
    vec3 ambientLight = $u_coef_ambient * v_color.rgb * $u_light_intensity;


    // ----------------- Diffuse light -----------------
    // Calculate the vector from this pixels surface to the light source
    vec3 surfaceToLight = $u_light_position - v_position;

    // Calculate the cosine of the angle of incidence
    float l_surf_norm = length(surfaceToLight) * length(v_normal);
    float brightness = dot(v_normal, surfaceToLight) / l_surf_norm;
    // brightness = clamp(brightness, 0, 1);
    brightness = max(min(brightness, 1.0), 0.0);

    // Get diffuse light :
    vec3 diffuseLight =  v_color.rgb * brightness * $u_light_intensity;


    // ----------------- Specular light -----------------
    vec3 surfaceToCamera = vec3(0.0, 0.0, 1.0) - v_position;
    vec3 K = normalize(normalize(surfaceToLight) + normalize(surfaceToCamera));
    float specular = clamp(pow(abs(dot(v_normal, K)), 40.), 0.0, 1.0);
    specular *= $u_coef_specular;
    vec3 specularLight = specular * vec3(1., 1., 1.) * $u_light_intensity;


    // ----------------- Attenuation -----------------
    // float att = 0.0001;
    // float distanceToLight = length($u_light_position - v_position);
    // float attenuation = 1.0 / (1.0 + att * pow(distanceToLight, 2));


    // ----------------- Linear color -----------------
    // Without attenuation :
    vec3 linearColor = ambientLight + specularLight + diffuseLight;

    // With attenuation :
    // vec3 linearColor = attenuation*(specularLight + diffuseLight);
    // linearColor += ambientLight

    // ----------------- Gamma correction -----------------
    // vec3 gamma = vec3(1.0/1.2);


    // ----------------- Final color -----------------
    // Without gamma correction :
    gl_FragColor = vec4(linearColor, $u_alpha);

    // With gamma correction :
    // gl_FragColor = vec4(pow(linearColor, gamma), $u_alpha);
}
"""


class BrainVisual(Visual):
    """Create and control a mesh of a 3D object.

    This class can be used to create a vispy compatible object. This object
    can then be wrap with a vispy.Node (which is convenient for adding
    transformations to it).
    The BrainVisual is the lowest level class to create a 3D MNI brain (or any
    type of 3D objects). Light is automatically ajust acording to camera
    rotations.

    Parameters
    ----------
    vertices : array_like | None
        Vertices to set of shape (N, 3) or (M, 3)
    faces : array_like | None
        Faces to set of shape (M, 3)
    normals : array_like | None
        The normals to set (same shape as vertices)
    camera : vispy | None
        Add a camera to the mesh. This object must be a vispy edfault
        camera.
    meshdata : vispy.meshdata | None
        Custom vispy mesh data
    color : tuple/string/hex | None
        Alternatively, you can specify a uniform color.
    l_position : tuple | (1., 1., 1.)
        Tuple of three floats defining (x, y, z) light position.
    l_color : tuple | (1., 1., 1., 1.)
        Tuple of four floats defining (R, G, B, A) light color.
    l_intensity : tuple | (1., 1., 1.)
        Tuple of three floats defining (x, y, z) light intensity.
    l_ambient : float | 0.05
        Coefficient for the ambient light
    l_specular : float | 0.5
        Coefficient for the specular light
    hemisphere : string | 'both'
        Choose if an hemisphere has to be selected ('both', 'left', 'right')
    lr_index : int | None
        Integer which specify the index where to split left and right
        hemisphere.
    vertfcn : VisPy.transform | None
        Transformation to apply to vertices using get_vertices.
    """

    def __len__(self):
        """Return the length of faces."""
        return len(self._vertices)

    def __iter__(self):
        """Iteration function."""
        pass

    def __getitem__(self):
        """Get a specific item."""
        pass

    def __init__(self, vertices=None, faces=None, normals=None, lr_index=None,
                 hemisphere='both', alpha=1., light_position=[100.] * 3,
                 light_color=[1.] * 4, light_intensity=[1.] * 3,
                 coef_ambient=.05, coef_specular=.5, vertfcn=None, camera=None,
                 meshdata=None):
        """Init."""
        self._camera = None
        self._camera_transform = vist.NullTransform()
        self._translucent = True
        self._alpha = alpha
        self._hemisphere = hemisphere

        # Initialize the vispy.Visual class with the vertex / fragment buffer :
        Visual.__init__(self, vcode=VERT_SHADER, fcode=FRAG_SHADER)

        # _________________ TRANSFORMATIONS _________________
        self._vertfcn = vist.NullTransform() if vertfcn is None else vertfcn

        # _________________ BUFFERS _________________
        # Vertices / faces / normals / color :
        def_3 = np.zeros((0, 3), dtype=np.float32)
        def_4 = np.zeros((0, 4), dtype=np.float32)
        self._vert_buffer = gloo.VertexBuffer(def_3)
        self._index_buffer = gloo.IndexBuffer()
        self._color_buffer = gloo.VertexBuffer(def_4)
        self._normals_buffer = gloo.VertexBuffer(def_3)

        # _________________ PROGRAMS _________________
        self.shared_program.vert['a_position'] = self._vert_buffer
        self.shared_program.vert['a_color'] = self._color_buffer
        self.shared_program.vert['a_normal'] = self._normals_buffer
        self.shared_program.frag['u_alpha'] = alpha

        # _________________ DATA / CAMERA / LIGHT _________________
        self.set_data(vertices, faces, normals, hemisphere, lr_index)
        self.set_camera(camera)
        self.light_color = light_color
        self.light_position = light_position
        self.light_intensity = light_intensity
        self.coef_ambient = coef_ambient
        self.coef_specular = coef_specular

        # _________________ GL STATE _________________
        self.set_gl_state('translucent', depth_test=True, cull_face=False,
                          blend=True, blend_func=('src_alpha',
                                                  'one_minus_src_alpha'))
        self._draw_mode = 'triangles'
        self.freeze()

    # =======================================================================
    # =======================================================================
    # Set data / light / camera / clean
    # =======================================================================
    # =======================================================================
    def set_data(self, vertices=None, faces=None, normals=None,
                 hemisphere='both', lr_index=None, meshdata=None,
                 invert_normals=False):
        """Set data to the mesh.

        Parameters
        ----------
        vertices : ndarray | None
            Vertices to set of shape (N, 3) or (M, 3)
        faces : ndarray | None
            Faces to set of shape (M, 3)
        normals : ndarray | None
            The normals to set (same shape as vertices)
        meshdata : vispy.meshdata | None
            Custom vispy mesh data
        hemisphere : string | 'both'
            Choose if an hemisphere has to be selected ('both', 'left',
            'right')
        invert_normals : bool | False
            Sometimes it appear that the brain color is full
            black. In that case, turn this parameter to True
            in order to invert normals.
        """
        # ____________________ VERTICES / FACES / NORMALS ____________________
        vertices, faces, normals = convert_meshdata(vertices, faces, normals,
                                                    meshdata, invert_normals)
        self._vertices = vertices
        self._faces = faces
        # Keep shapes :
        self._shapes = np.zeros(1, dtype=[('vert', int), ('faces', int)])
        self._shapes['vert'] = vertices.shape[0]
        self._shapes['faces'] = faces.shape[0]

        # Find ratio for the camera :
        v_max, v_min = vertices.max(0), vertices.min(0)
        self._center = (v_max + v_min).astype(float) / 2.
        self._camratio = (v_max - v_min).astype(float)

        # ____________________ HEMISPHERE ____________________
        if lr_index is None or len(lr_index) != vertices.shape[0]:
            lr_index = vertices[:, 0] <= vertices[:, 0].mean()
        self._lr_index = lr_index[faces[:, 0]]

        # ____________________ ASSIGN ____________________
        color = np.ones((vertices.shape[0], 4), dtype=np.float32)

        # ____________________ BUFFERS ____________________
        self._vert_buffer.set_data(vertices, convert=True)
        self._normals_buffer.set_data(normals, convert=True)
        self._color_buffer.set_data(color, convert=True)
        self.hemisphere = hemisphere

    def set_color(self, data=None, color='white', alpha=1.0, **kwargs):
        """Set specific colors on the brain.

        Parameters
        ----------
        data : array_like | None
            Data to use for the color. If data is None, the color will
            be uniform using the color parameter. If data is a vector,
            the color is going to be deduced from this vector. If data
            is a (N, 4) it will be interpreted as a color.
        color : tuple/string/hex | 'white'
            The default uniform color
        alpha : float | 1.0
            Opacity to use if data is a vector
        kwargs : dict | { }
            Further arguments are passed to the colormap function.
        """
        # Color to RGBA :
        color = color2vb(color, len(self))

        # Color management :
        if data is None:  # uniform color
            col = np.tile(color, (len(self), 1))
        elif data.ndim == 1:  # data vector
            col = array2colormap(data.copy(), **kwargs)
        elif (data.ndim > 1) and (data.shape[1] == 4):
            col = vispy_array(data)
        else:
            col = data

        self._color_buffer.set_data(vispy_array(col))
        self.update()

    def set_alpha(self, alpha, index=None):
        """Set transparency to the brain.

        Prameters
        ---------
        alpha : float
            Transparency level.
        index : array_like | None
            Index for sending alpha. Used by slices.
        """
        if index is None:
            self._colFaces[..., -1] = np.float32(alpha)
        else:
            self._colFaces[index, -1] = np.float32(alpha)
        self._color_buffer.set_data(self._colFaces)
        self.update()

    def set_camera(self, camera=None):
        """Set a camera to the mesh.

        This is essential to add to the mesh the link between the camera
        rotations (transformation) to the vertex shader.

        Parameters
        ----------
        camera : vispy.camera | None
            Set a camera to the Mesh for light adaptation
        """
        if camera is not None:
            self._camera = camera
            self._camera_transform = self._camera.transform
            self.update()

    def clean(self):
        """Clean the mesh.

        This method delete the object from GPU memory.
        """
        # Delete vertices / faces / colors / normals :
        self._vert_buffer.delete()
        self._index_buffer.delete()
        self._color_buffer.delete()
        self._normals_buffer.delete()

    # =======================================================================
    # =======================================================================
    # Drawing functions
    # =======================================================================
    # =======================================================================

    def draw(self, *args, **kwds):
        """Call when drawing only."""
        Visual.draw(self, *args, **kwds)

    def _prepare_draw(self, view=None):
        """Call everytime there is an interaction with the mesh."""
        view_frag = view.view_program.frag
        view_frag['u_light_position'] = self._camera_transform.map(
            self._light_position)[0:-1]

    @staticmethod
    def _prepare_transforms(view):
        """First rendering call."""
        tr = view.transforms
        transform = tr.get_transform()

        view_vert = view.view_program.vert
        view_vert['transform'] = transform

    # =======================================================================
    # =======================================================================
    # Properties
    # =======================================================================
    # =======================================================================

    @property
    def get_vertices(self):
        """Mesh data."""
        return self._vertfcn.map(self._vertices)[..., 0:-1]

    # ----------- HEMISPHERE -----------
    @property
    def hemisphere(self):
        """Get the hemisphere value."""
        return self._hemisphere

    @hemisphere.setter
    def hemisphere(self, value):
        """Set hemisphere value."""
        assert value in ['left', 'both', 'right']
        if value == 'both':
            index = self._faces
        elif value == 'left':
            index = self._faces[self._lr_index, :]
        elif value == 'right':
            index = self._faces[~self._lr_index, :]
        self._index_buffer.set_data(index)
        self.update()
        self._hemisphere = value

    # # ----------- COLOR -----------
    # @property
    # def color(self):
    #     """Get the color value."""
    #     return self._color

    # @color.setter
    # @wrap_properties
    # def color(self, value):
    #     """Set color value."""
    #     n_faces = self._shapes['faces'][0]
    #     if isinstance(value, str):
    #         value = color2vb(value, length=n_faces, faces_index=True)
    #     assert isinstance(value, np.ndarray) and value.ndim == 3
    #     assert value.shape[0] == n_faces
    #     self._color_buffer.set_data(value.astype(np.float32))
    #     self._colFaces = value

    # ----------- TRANSPARENT -----------
    @property
    def translucent(self):
        """Get the translucent value."""
        return self._translucent

    @translucent.setter
    @wrap_properties
    def translucent(self, value):
        """Set translucent value."""
        assert isinstance(value, bool)
        if value:
            self.set_gl_state('translucent', depth_test=False, cull_face=False)
            alpha = 0.1
        else:
            self.set_gl_state('translucent', depth_test=True, cull_face=False)
            alpha = 1.
        self._translucent = value
        self.alpha = alpha
        self.update_gl_state()

    # ----------- ALPHA -----------
    @property
    def alpha(self):
        """Get the alpha value."""
        return self._alpha

    @alpha.setter
    @wrap_properties
    def alpha(self, value):
        """Set alpha value."""
        assert isinstance(value, (int, float))
        value = min(value, .1) if self._translucent else 1.
        self._alpha = value
        self.shared_program.frag['u_alpha'] = value
        self.update()

    # ----------- LIGHT_POSITION -----------
    @property
    def light_position(self):
        """Get the light_position value."""
        return self._light_position

    @light_position.setter
    @wrap_properties
    def light_position(self, value):
        """Set light_position value."""
        assert len(value) == 3
        self.shared_program.frag['u_light_position'] = value
        self._light_position = value
        self.update()

    # ----------- LIGHT_COLOR -----------
    @property
    def light_color(self):
        """Get the light_color value."""
        return self._light_color

    @light_color.setter
    @wrap_properties
    def light_color(self, value):
        """Set light_color value."""
        assert len(value) == 4
        self.shared_program.vert['u_light_color'] = value
        self._light_color = value
        self.update()

    # ----------- LIGHT_INTENSITY -----------
    @property
    def light_intensity(self):
        """Get the light_intensity value."""
        return self._light_intensity

    @light_intensity.setter
    @wrap_properties
    def light_intensity(self, value):
        """Set light_intensity value."""
        assert len(value) == 3
        self.shared_program.frag['u_light_intensity'] = value
        self._light_intensity = value
        self.update()

    # ----------- COEF_AMBIENT -----------
    @property
    def coef_ambient(self):
        """Get the coef_ambient value."""
        return self._coef_ambient

    @coef_ambient.setter
    @wrap_properties
    def coef_ambient(self, value):
        """Set coef_ambient value."""
        assert isinstance(value, (int, float))
        self.shared_program.frag['u_coef_ambient'] = float(value)
        self._coef_ambient = value
        self.update()

    # ----------- COEF_SPECULAR -----------
    @property
    def coef_specular(self):
        """Get the coef_specular value."""
        return self._coef_specular

    @coef_specular.setter
    @wrap_properties
    def coef_specular(self, value):
        """Set coef_specular value."""
        assert isinstance(value, (int, float))
        self.shared_program.frag['u_coef_specular'] = value
        self._coef_specular = value
        self.update()


BrainMesh = create_visual_node(BrainVisual)
