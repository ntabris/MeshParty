import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
import numpy as np


def numpy_to_vtk_cells(mat):
    """function to convert a numpy array of integers to a vtkCellArray

    Parameters
    ----------
    mat : np.array
        MxN array to be converted
    
    Returns
    -------
    vtk.vtkCellArray
        representing the numpy array, has the same shaped cell (N) at each of the M indices

    """


    cells = vtk.vtkCellArray()

    # Seemingly, VTK may be compiled as 32 bit or 64 bit.
    # We need to make sure that we convert the trilist to the correct dtype
    # based on this. See numpy_to_vtkIdTypeArray() for details.
    isize = vtk.vtkIdTypeArray().GetDataTypeSize()
    req_dtype = np.int32 if isize == 4 else np.int64
    n_elems = mat.shape[0]
    n_dim = mat.shape[1]
    cells.SetCells(n_elems,
                   numpy_to_vtkIdTypeArray(
                       np.hstack((np.ones(n_elems)[:, None] * n_dim,
                                  mat)).astype(req_dtype).ravel(),
                       deep=1))
    return cells


def numpy_rep_to_vtk(vertices, shapes, edges=None):
    """ converts a numpy representation of vertices and vertex connection graph
      to a polydata object and corresponding cell array

    Parameters
    ----------
    vertices: a Nx3 numpy array of vertex locations
    shapes: a MxK numpy array of vertex connectivity
                       (could be triangles (K=3) or edges (K=2))

    Returns
    -------
    vtk.vtkPolyData
        a polydata object with point set according to vertices,
    vtkCellArray
        a vtkCellArray of the shapes

    """

    mesh = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(vertices, deep=1))
    mesh.SetPoints(points)

    cells = numpy_to_vtk_cells(shapes)
    if edges is not None:
        if len(edges)>0:
            edges = numpy_to_vtk_cells(edges)
        else:
            edges = None

    return mesh, cells, edges


def graph_to_vtk(vertices, edges):
    """ converts a numpy representation of vertices and edges
      to a vtkPolyData object

    Parameters
    ----------
    vertices: np.array
        a Nx3 numpy array of vertex locations
    edges: np.array
        a Mx2 numpy array of vertex connectivity
        where the values are the indexes of connected vertices

    Returns
    -------
    vtk.vtkPolyData
        a polydata object with point set according to vertices
        and edges as its Lines

    Raises
    ------
    ValueError
        if edges is not 2d or refers to out of bounds vertices

    """
    if edges.shape[1] != 2:
        raise ValueError('graph_to_vtk() only works on edge lists')
    if np.max(edges) >= len(vertices):
        msg = 'edges refer to non existent vertices {}.'
        raise ValueError(msg.format(np.max(edges)))
    mesh, cells, edges = numpy_rep_to_vtk(vertices, edges)
    mesh.SetLines(cells)
    return mesh


def trimesh_to_vtk(vertices, tris, graph_edges=None):
    """Return a `vtkPolyData` representation of a :obj:`TriMesh` instance

    Parameters
    ----------
    vertices : np.array
        numpy array of Nx3 vertex positions (x,y,z)
    tris: np.array
        numpy array of Mx3 triangle vertex indices (int64)
    graph_edges: np.array
        numpy array of Kx2 of edges to set as the vtkPolyData.Lines

    Returns
    -------
    vtk_mesh : vtk.vtkPolyData
        A VTK mesh representation of the mesh :obj:`trimesh.TriMesh` data

    Raises
    ------
    ValueError:
        If the input trimesh is not 3D
        or tris refers to out of bounds vertex indices

    """

    if tris.shape[1] != 3:
        raise ValueError('trimesh_to_vtk() only works on 3D TriMesh instances')
    if np.max(tris) >= len(vertices):
        msg = 'edges refer to non existent vertices {}.'
        raise ValueError(msg.format(np.max(tris)))
    mesh, cells, edges = numpy_rep_to_vtk(vertices, tris, graph_edges)
    mesh.SetPolys(cells)
    if edges is not None:
        mesh.SetLines(edges)

    return mesh


def vtk_cellarray_to_shape(vtk_cellarray, ncells):
    """Turn a vtkCellArray into a numpyarray of a fixed shape
    assumes your cell array has uniformed sized cells

    Parameters
    ----------
    vtk_cellarray : vtk.vtkCellArray
        a cell array to convert
    ncells: int
        how many cells are in array

    Returns
    -------
    np.array
        cellarray, a ncells x K array of cells, where K is the
        uniform shape of the cells.  Will error if cells are not uniform

    """
    cellarray = vtk_to_numpy(vtk_cellarray)
    cellarray = cellarray.reshape(ncells, int(len(cellarray)/ncells))
    return cellarray[:, 1:]


def decimate_trimesh(trimesh, reduction=.1):
    """ routine to decimate a mesh through vtk

    Parameters
    ----------
    trimesh : trimesh_io.Mesh
        a mesh to decimate
    reduction: float
        factor to decimate (default .1)

    Returns
    -------
    np.array
        points, the Nx3 mesh of vertices
    np.array
        tris, the Kx3 indices of faces

    """

    poly = trimesh_to_vtk(trimesh.vertices, trimesh.faces)
    dec = vtk.vtkDecimatePro()
    dec.SetTargetReduction(reduction)
    dec.PreserveTopologyOn()
    dec.SetInputData(poly)
    dec.Update()
    out_poly = dec.GetOutput()

    points = vtk_to_numpy(out_poly.GetPoints().GetData())
    ntris = out_poly.GetNumberOfPolys()
    tris = vtk_cellarray_to_shape(out_poly.GetPolys().GetData(), ntris)
    return points, tris


def remove_unused_verts(verts, faces):
    """removes unused vertices from a graph or mesh

    Parameters
    ----------
    verts : np.array
        NxD numpy array of vertex locations
    faces : np.array
        MxK numpy array of connected shapes (i.e. edges or tris)
        (entries are indices into verts)
    
    Returns
    -------
    np.array
        new_verts a filtered set of vertices s
    new_face
        a reindexed set of faces

    """
    used_verts = np.unique(faces.ravel())
    new_verts = verts[used_verts, :]
    new_face = np.zeros(faces.shape, dtype=faces.dtype)
    for i in range(faces.shape[1]):
        new_face[:, i] = np.searchsorted(used_verts, faces[:, i])
    return new_verts, new_face


def poly_to_mesh_components(poly):
    """ converts a vtkPolyData to its numpy components

    Parameters
    ----------
    poly : vtk.vtkPolyData
        a polydate object to convert to numpy components
    
    Returns
    -------
    np.array
        points, the Nx3 set of vertex locations
    np.array
        tris, the KxD set of faces (assumes a uniform cellarray)
    np.array
        edges, if exists uses the GetLines to make edges

    """
    points = vtk_to_numpy(poly.GetPoints().GetData())
    ntris = poly.GetNumberOfPolys()
    if ntris > 0:
       tris = vtk_cellarray_to_shape(poly.GetPolys().GetData(), ntris)
    else:
        tris = None     
    nedges = poly.GetNumberOfLines()
    if nedges > 0:
        edges = vtk_cellarray_to_shape(poly.GetLines().GetData(), nedges)
    else:
        edges = None
    return points, tris, edges


def render_actors(actors, camera=None, do_save=False, filename=None,
                  scale=4, back_color=(1, 1, 1),
                  VIDEO_WIDTH=1080, VIDEO_HEIGHT=720):
    """
    Visualize a set of actors in a 3d scene, optionally saving a snapshot. 
    Creates a window, renderer, interactor, add the actors and starts the visualization
    (can save images and close render window)

    Parameters
    ----------
    actors :  list[vtkActor]
        list of actors to render (see mesh_actor, point_cloud_actor, skeleton_actor)
    camera : :obj:`vtkCamera`
        camera to use for scence (optional..default to fit scene)
    do_save: bool
        write png image to disk, if false will open interactive window (default False)
    filename: str
        filepath to save png image to (default None)
    scale: 
        scale factor to use when saving images to disk (default 4) for higher res images
    back_color: Iterable
        rgb values (0,1) to determine for background color (default 1,1,1 = white)

    Returns
    -------
    :obj:`vtk.vtkRenderer`
        renderer when code was finished
        (useful for retrieving user input camera position ren.GetActiveCamera())

    """
    if do_save:
        assert(filename is not None)
    # create a rendering window and renderer
    ren = vtk.vtkRenderer()
    ren.UseFXAAOn()
    if camera is not None:
        ren.SetActiveCamera(camera)

    renWin = vtk.vtkRenderWindow()
    renWin.AddRenderer(ren)
    renWin.SetSize(VIDEO_WIDTH, VIDEO_HEIGHT)
    # renderWindow.SetAlphaBitPlanes(1)

    ren.SetBackground(*back_color)
    # create a renderwindowinteractor
    iren = vtk.vtkRenderWindowInteractor()
    iren.SetRenderWindow(renWin)

    for a in actors:
        # assign actor to the renderer
        ren.AddActor(a)

    # render
    if camera is None:
        ren.ResetCamera()
    else:
        ren.SetActiveCamera(camera)
        ren.ResetCameraClippingRange()
        camera.ViewingRaysModified()
    renWin.Render()


    if do_save is False:
        trackCamera = vtk.vtkInteractorStyleTrackballCamera()
        iren.SetInteractorStyle(trackCamera)
        # enable user interface interactor
        iren.Initialize()
        iren.Render()
        iren.Start()


    if do_save is True:
        renWin.OffScreenRenderingOn()
        w2if = vtk.vtkWindowToImageFilter()
        w2if.SetScale(scale)
        w2if.SetInput(renWin)
        w2if.Update()

        writer = vtk.vtkPNGWriter()
        writer.SetFileName(filename)
        writer.SetInputData(w2if.GetOutput())
        writer.Write()

    renWin.Finalize()

    return ren


def camera_from_quat(pos_nm, orient_quat, camera_distance=10000, ngl_correct=True):
    """define a vtk camera with a particular orientation

    Parameters
    ----------
    pos_nm: np.array, list, tuple
        an iterator of length 3 containing the focus point of the camera
    orient_quat: np.array, list, tuple
        a len(4) quatenerion (x,y,z,w) describing the rotation of the camera
        such as returned by neuroglancer x,y,z,w all in [0,1] range
    camera_distance: float
        the desired distance from pos_nm to the camera (default = 10000 nm)

    Returns
    -------
    vtk.vtkCamera
        a vtk camera setup according to these rules

    """
    camera = vtk.vtkCamera()
    # define the quaternion in vtk, note the swapped order
    # w,x,y,z instead of x,y,z,w
    quat_vtk=vtk.vtkQuaterniond(orient_quat[3],
                                orient_quat[0],
                                orient_quat[1],
                                orient_quat[2])
    # use this to define a rotation matrix in x,y,z
    # right handed units
    M = np.zeros((3, 3), dtype=np.float32)
    quat_vtk.ToMatrix3x3(M)
    # the default camera orientation is y up
    up = [0, 1, 0]
    # calculate default camera position is backed off in positive z 
    pos = [0, 0, camera_distance]
    
    # set the camera rototation by applying the rotation matrix
    camera.SetViewUp(*np.dot(M,up))
    # set the camera position by applying the rotation matrix
    camera.SetPosition(*np.dot(M,pos))
    if ngl_correct:
        # neuroglancer has positive y going down
        # so apply these azimuth and roll corrections
        # to fix orientatins
        camera.Azimuth(-180)
        camera.Roll(180)

    # shift the camera posiiton and focal position
    # to be centered on the desired location
    p=camera.GetPosition()
    p_new = np.array(p)+pos_nm
    camera.SetPosition(*p_new)
    camera.SetFocalPoint(*pos_nm)
    return camera

def camera_from_ngl_state(state_d, zoom_factor=300.0):
    """define a vtk camera from a neuroglancer state dictionary
    
    Parameters
    ----------
    state_d: dict
        an neuroglancer state dictionary
    zoom_factor: float
        how much to multiply zoom by to get camera backoff distance
        default = 300 > ngl_zoom = 1 > 300 nm backoff distance

    Returns
    -------
    vtk.vtkCamera
        a vtk camera setup that mathces this state

    """

    orient = state_d.get('perspectiveOrientation', [0.0,0.0,0.0,1.0])
    zoom = state_d.get('perspectiveZoom', 10.0)
    position = state_d['navigation']['pose']['position']
    pos_nm = np.array(position['voxelCoordinates'])*position['voxelSize']
    camera = camera_from_quat(pos_nm, orient, zoom*zoom_factor, ngl_correct=True)
    
    return camera


def process_colors(color,xyz):
    """ utility function to normalize colors on an set of things

    Parameters
    ----------
    color : np.array
        a Nx3, or a N long, or a 3 long iterator the represents the 
        color or colors  you want to label xyz with
    xyz: np.array
        a NxD matrix you wish to 'color'
    
    Returns
    -------
    np.array
        a Nx3 or N long array of color values
    bool
        map_colors, whether the colors should be mapped through a colormap
        or used as is

    """
    map_colors = False
    if not isinstance(color, np.ndarray):
        color = np.array(color)
    if color.shape == (len(xyz),3):
        # then we have explicit colors
        if color.dtype != np.uint8:
            # if not passing uint8 assume 0-1 mapping
            assert(np.max(color)<=1.0)
            assert(np.min(color)>=0)
            color = np.uint8(color*255)
    elif color.shape ==(len(xyz),):
        # then we want to map colors
        map_colors = True     
    elif color.shape == (3,):
        # then we have one explicit color
        assert(np.max(color)<=1.0)
        assert(np.min(color)>=0)
        car = np.array(color, dtype=np.uint8)*255 
        color = np.repeat(car[np.newaxis,:],len(xyz),axis=0)
    else:
        raise ValueError('color must have shapse Nx3 if explicitly setting, or (N,) if mapping, or (3,)')
    return color, map_colors

def mesh_actor(mesh,
               color=(0, 1, 0),
               opacity=0.1,
               vertex_colors=None,
               face_colors=None,
               lut=None,
               calc_normals=True,
               show_link_edges=False,
               line_width=3):
    """ function for producing a vtkActor from a trimesh_io.Mesh

    Parameters
    ----------
    mesh : trimesh_io.Mesh
        a mesh to visualize
    color: various
        a len 3 iterator of a solid color to label mesh
        overridden by vertex_colors if passed
    opacity: float
        the opacity of the mesh (default .1)
    vertex_colors: np.array
        a np.array Nx3 list of explicit colors  (where N is len(mesh.vertices))
        OR
        a np.array of len(N) list of values to map through a colormap
        default (None) will use color to color mesh
    face_colors: np.array
        a np.array of Mx3 list of explicit colors (where M is the len(mesh.faces))
        OR
        a np.array of len(M) list of values to map through a colormap
        (default None will use color for mesh)
    lut: np.array
        not implemented
    calc_normals: bool
        whether to calculate normals on the mesh.  Default (True)
        will take more time, but will render a smoother mesh
        not compatible with sbow_link_edges. default True
    show_link_edges: bool
        whether to show the link_edges as lines. Will prevent calc_normals.
        default False
    line_width: int
        how thick to show lines (default 3)

    Returns
    -------
    vtk.vtkActor
        vtkActor representing the mesh (to be passed to render_actors)

    """
    if show_link_edges:
        mesh_poly = trimesh_to_vtk(mesh.vertices, mesh.faces, mesh.link_edges)
    else:
        mesh_poly = trimesh_to_vtk(mesh.vertices, mesh.faces, None)
    if vertex_colors is not None:
        vertex_color, map_vertex_color =  process_colors(vertex_colors, mesh.vertices)
        vtk_vert_colors = numpy_to_vtk(vertex_color)
        vtk_vert_colors.SetName('colors')
        mesh_poly.GetPointData().SetScalars(vtk_vert_colors)
    
    if face_colors is not None:
        face_color, map_face_colors = process_colors(face_colors, mesh.faces)
        vtk_face_colors = numpy_to_vtk(face_color)
        vtk_face_colors.SetName('colors')
        mesh_poly.GetCellData().SetScalars(vtk_face_colors)

    mesh_mapper = vtk.vtkPolyDataMapper()
    if calc_normals and (not show_link_edges):
        norms = vtk.vtkTriangleMeshPointNormals()
        norms.SetInputData(mesh_poly)
        mesh_mapper.SetInputConnection(norms.GetOutputPort())
    else:
        mesh_mapper.SetInputData(mesh_poly)

    mesh_actor = vtk.vtkActor()

    if lut is not None:
        mesh_mapper.SetLookupTable(lut)
        if face_colors is not None:
            if map_face_colors:
                mesh_mapper.SelectColorArray('colors')
    mesh_mapper.ScalarVisibilityOn()
    mesh_actor.SetMapper(mesh_mapper)
    mesh_actor.GetProperty().SetLineWidth(line_width)
    mesh_actor.GetProperty().SetColor(*color)
    mesh_actor.GetProperty().SetOpacity(opacity)
    return mesh_actor


def skeleton_actor(sk,
                   edge_property=None,
                   vertex_property=None,
                   vertex_data=None,
                   normalize_property=True,
                   color=(0, 0, 0),
                   line_width=3,
                   opacity=0.7,
                   lut_map=None):
    """
    function to make a vtkActor from a skeleton class with different coloring options

    Parameters
    ----------
    sk : skeleton.Skeleton
        the skeleton class to create a render
    edge_property: str
        the key to the edge_properties dictionary on the sk object to use for coloring
        default None .. use color instead
    vertex_property: str
        the key to the vertex_properteis dictionary on the sk object to use for coloring
        default NOne ... use color instead
    vertex_data: np.array
        what data to color skeleton vertices by
        default None... use color intead
    normalize_property: bool
        whether to normalize the property data (edge/vertex) with dividing by np.nanmax
    color: tuple
        a 3 tuple in the [0,1] range of the color of the skeletoni
    line_width: int
        the width of the skeleton (default 3)
    opacity: float
        the opacity [0,1] of the mesh (1 = opaque, 0 = invisible)
    lut_map: np.array
        not implemented

    Returns
    -------
    vtk.vtkActor
        actor representing the skeleton

    """
    sk_mesh = graph_to_vtk(sk.vertices, sk.edges)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(sk_mesh)
    if edge_property is not None:
        data = sk.edge_properties[edge_property]
        if normalize_property:
            data = data / np.nanmax(data)
        sk_mesh.GetCellData().SetScalars(numpy_to_vtk(data))
        lut = vtk.vtkLookupTable()
        if lut_map is not None:
            lut_map(lut)
        lut.Build()
        mapper.SetLookupTable(lut)

    data = None
    if vertex_data is None and vertex_property is not None:
        data = sk.vertex_properties[vertex_property]
    else:
        data = vertex_data

    if data is not None:
        if normalize_property:
            data = data / np.nanmax(data)
        sk_mesh.GetPointData().SetScalars(numpy_to_vtk(data))
        lut = vtk.vtkLookupTable()
        if lut_map is not None:
            lut_map(lut)
        lut.Build()
        mapper.ScalarVisibilityOn()
        mapper.SetLookupTable(lut)

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetLineWidth(line_width)
    actor.GetProperty().SetOpacity(opacity)
    actor.GetProperty().SetColor(color)
    return actor

def point_cloud_actor(xyz,
                     size=100,
                     color=(0,0,0),
                     opacity=0.5):
    """function to make a vtk.vtkActor from a set of xyz points that renders them as spheres

    Parameters
    ----------
    xyz : np.array
        a Nx3 array of points
    size: float or np.array
        the size of each of the points, or a N long array of sizes of each point
    color: len(3) iterator or np.array
        the color of all the points, or the color of each point individually as a N long array
        or a Nx3 list of explicit colors [0,1] range
    opacity: float
        the [0,1] opacity of mesh
    
    Returns
    -------
    vtk.vtkActor
        an actor with each of the xyz points as spheres of the specified size and color

    """
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(xyz, deep=True))

    pc = vtk.vtkPolyData() 
    pc.SetPoints(points)

    color, map_colors = process_colors(color, xyz)

    vtk_colors = numpy_to_vtk(color)
    vtk_colors.SetName('colors')

    if np.isscalar(size):
        size = np.full(len(xyz), size)
    elif len(size) != len(xyz):
        raise ValueError('Size must be either a scalar or an len(xyz) x 1 array')
    pc.GetPointData().SetScalars(numpy_to_vtk(size))
    pc.GetPointData().AddArray(vtk_colors)

    ss = vtk.vtkSphereSource()
    ss.SetRadius(1)

    glyph = vtk.vtkGlyph3D()
    glyph.SetInputData(pc)
    glyph.SetInputArrayToProcess(3, 0, 0, 0, "colors")
    glyph.SetColorModeToColorByScalar()
    glyph.SetSourceConnection(ss.GetOutputPort())
    glyph.SetScaleModeToScaleByScalar()
    glyph.ScalingOn()
    glyph.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(glyph.GetOutputPort())
    if map_colors:
        mapper.SetScalarRange(np.min(color), np.max(color))
        mapper.SelectColorArray('colors')
    
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    return actor


def linked_point_actor(vertices_a, vertices_b,
                       inds_a=None, inds_b=None,
                       line_width=1, color=(0, 0, 0), opacity=0.2):
    """ function for making polydata with lines between pairs of points

    Parameters
    ----------
    vertices_a : np.array
        a Nx3 array of point locations in xyz
    vertices_b : np.array
        a Nx3 array of point locations in xyz
    inds_a: np.array
        the indices in vertices_a to use (default None is all of them)
    inds_b: np.array
        the indices in vertices_b to use (default None is all of them)
    line_width : int
        the width of lines to draw (default 1)
    color : iterator
        a len(3) iterator (tuple, list, np.array) with the color [0,1] to use
    opacity: float
         a [0,1] opacity to render the lines
        
    Returns
    -------
    vtk.vtkActor
        an actor representing the lines between the points given with the color and opacity
        specified. To be passed to render_actors

    """
    if inds_a is None:
        inds_a = np.arange(len(vertices_a))
    if inds_b is None:
        inds_b = np.arange(len(vertices_b))

    if len(inds_a) != len(inds_b):
        raise ValueError('Linked points must have the same length')

    link_verts = np.vstack((vertices_a[inds_a], vertices_b[inds_b]))
    link_edges = np.vstack((np.arange(len(inds_a)),
                            len(inds_a)+np.arange(len(inds_b))))
    link_poly = graph_to_vtk(link_verts, link_edges.T)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(link_poly)

    link_actor = vtk.vtkActor()
    link_actor.SetMapper(mapper)
    link_actor.GetProperty().SetLineWidth(line_width)
    link_actor.GetProperty().SetColor(color)
    link_actor.GetProperty().SetOpacity(opacity)
    return link_actor


def oriented_camera(center, up_vector=(0, -1, 0), backoff=500, backoff_vector=(0,0,1)):
    '''
    Generate a camera pointed at a specific location, oriented with a given up
    direction, set to a backoff of the center a fixed distance with a particular direction

    Parameters
    ----------
    center : iterator
        a len 3 iterator (tuple, list, np.array) with the x,y,z location of the camera's focus point
    up_vector: iterator
        a len 3 iterator (tuple, list, np.array) with the dx,dy,dz direction of the camera's up direction
        default (0,-1,0) negative y is up.
    backoff: float
        distance in global space for the camera to be moved backward from the center point (default 500)
    backoff_vector: iterator
        a len 3 iterator (tuple, list, np.array) with the dx,dy,dz direction to back camera off of the focus point
    
    Returns
    -------
    vtk.vtkCamera
        the camera object representing the desired camera location, orientation and focus parameters

    '''
    camera = vtk.vtkCamera()

    pt_center = center

    vup=np.array(up_vector)
    vup=vup/np.linalg.norm(vup)

    bv = np.array(backoff_vector)
    pt_backoff = pt_center - backoff * 1000 * bv

    camera.SetFocalPoint(*pt_center)
    camera.SetViewUp(*vup)
    camera.SetPosition(*pt_backoff)
    return camera


def scale_bar_actor(center, camera, length=10000, color=(0,0,0), linewidth=5, font_size=20):
    """Creates a xyz 3d scale bar actor located at a specific location with a given size
    
    Parameters
    ----------
    center : iterable
        a length 3 iterable of xyz position
    camera : vtk.vtkCamera
        the camera the scale bar should follow
    length : int, optional
        length of each of the xyz axis, by default 10000
    color : tuple, optional
        color of text and lines, by default (0,0,0)
    linewidth : int, optional
        width of line in pixels, by default 5
    font_size : int, optional
        font size of xyz labels, by default 20

    Returns
    -------
    vtk.vktActor
        scale bar actor to add to render_actors

    """
    axes_actor = vtk.vtkCubeAxesActor2D()
    axes_actor.SetBounds(center[0], center[0]+length,
                         center[1], center[1]+length,
                         center[2], center[2]+length)
    # this means no real labels
    axes_actor.SetLabelFormat("")
    axes_actor.SetCamera(camera)
    # this turns off the tick marks and labelled numbers
    axes_actor.SetNumberOfLabels(0)
    # this affects whether the corner of the 3 axis
    # changes as you rotate the view
    # this option makes it stay constant
    axes_actor.SetFlyModeToNone()
    axes_actor.SetFontFactor(1.0)
    axes_actor.GetProperty().SetColor(*color)
    axes_actor.GetProperty().SetLineWidth(linewidth)
    # this controls the color of text
    tprop =vtk.vtkTextProperty()
    tprop.SetColor(*color)
    # no shadows on text
    tprop.ShadowOff()
    tprop.SetFontSize(font_size)
    # makes the xyz and labels the same
    axes_actor.SetAxisTitleTextProperty(tprop)
    axes_actor.SetAxisLabelTextProperty(tprop)

    return axes_actor
