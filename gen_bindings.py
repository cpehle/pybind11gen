#!/usr/local/bin/python2.7
import sys
import os
import platform
import argparse
import subprocess
import clang.cindex

def get_annotations(node):
    return [c.displayname for c in node.get_children()
            if c.kind == clang.cindex.CursorKind.ANNOTATE_ATTR]

class Enum(object):
    def __init__(self, cursor, namespace):
        self.name = cursor.spelling
        self.annotations = get_annotations(cursor)
        self.access = cursor.access_specifier
        self.values = []
        self.namespace = namespace
        for c in cursor.get_children():
            self.values.append({'name': c.spelling, 'doc': c.brief_comment})

class Constructor(object):
    def __init__(self, cursor):
        self.annotations = get_annotations(cursor)
        self.access = cursor.access_specifier
        self.arguments = []
        self.argument_types = []
        
        for c in cursor.get_children():
            if (c.kind == clang.cindex.CursorKind.PARM_DECL):
                self.argument_types.append(c.type.get_canonical().spelling)
                self.arguments.append(c.spelling)
                    
class Function(object):
    def __init__(self, cursor, namespace):
        self.name = cursor.spelling
        self.namespace = namespace
        self.comment = cursor.brief_comment
        self.annotations = get_annotations(cursor)
        self.access = cursor.access_specifier

class Field(object):
    def __init__(self, cursor):
        self.name = cursor.spelling
        self.comment = cursor.brief_comment
        self.annotations = get_annotations(cursor)
        self.access = cursor.access_specifier
        
class Class(object):
    def __init__(self, cursor, namespace):
        self.name = cursor.spelling
        self.comment = cursor.brief_comment
        self.inherit = []
        self.namespace = namespace
        self.functions = []
        self.fields = []
        self.constructors = []
        self.classes = []
        self.enums = []
        self.annotations = get_annotations(cursor)

        for c in cursor.get_children():
            if (c.kind == clang.cindex.CursorKind.CXX_BASE_SPECIFIER):
                self.inherit.append(c.spelling.strip('class '))                                    
            if (c.kind == clang.cindex.CursorKind.CXX_METHOD and
                c.access_specifier == clang.cindex.AccessSpecifier.PUBLIC):
                f = Function(c, namespace)
                self.functions.append(f)
            if (c.kind == clang.cindex.CursorKind.CONSTRUCTOR):
                f = Constructor(c)
                self.constructors.append(f)
            if (c.kind == clang.cindex.CursorKind.FIELD_DECL and c.access_specifier == clang.cindex.AccessSpecifier.PUBLIC):
                f = Field(c)
                self.fields.append(f)

            if (c.kind == clang.cindex.CursorKind.ENUM_DECL):
                f = Enum(c, self.namespace + '::' + self.name)
                self.enums.append(f)
            
            if (c.kind == clang.cindex.CursorKind.CLASS_DECL or c.kind == clang.cindex.CursorKind.STRUCT_DECL):
                f = Class(c, self.namespace + '::' + self.name)
                self.classes.append(f)

def build_declarations(cursor, filename, namespace = ''):
    result = []
    for c in cursor.get_children():
        if ((c.kind == clang.cindex.CursorKind.ENUM_DECL) and c.location.file.name == filename):
            f = Enum(c, namespace)
            result.append(f)
        if ((c.kind == clang.cindex.CursorKind.FUNCTION_DECL) and c.location.file.name == filename):
            f = Function(c, namespace)
            result.append(f)        
        if ((c.kind == clang.cindex.CursorKind.CLASS_DECL or c.kind == clang.cindex.CursorKind.STRUCT_DECL)
            and c.location.file.name == filename):
            a_class = Class(c, namespace)
            result.append(a_class)
        elif c.kind == clang.cindex.CursorKind.NAMESPACE:
            if namespace == '':
                child_classes = build_declarations(c, filename, c.spelling)
            else:
                child_classes = build_declarations(c, filename, namespace + '::' + c.spelling)
            result.extend(child_classes)
    return result

def print_function(c, ctx_name, o):
    o.append(ctx_name + '.def("' + c.name + '", &' + c.namespace + '::' + c.name)
    if c.comment:
        o.append(',"' + c.comment + '"')
    o.append(');')

def print_enum(c, ctx_name, o):
    o.append('py::emum_<' + c.namespace + '::' + c.name + '>(m, "' + c.name + '")')
    for v in c.values:
        o.append('.value("' + v['name'] + '",' + c.namespace + '::' + c.name + '::' + v['name'] + ')') 
    o.append(';')

def print_class(c, ctx_name, o):
    for f in c.enums:
        o.append('py::emum_<' + c.namespace + '::' + c.name + '::' + f.name + '>(m, "' + f.name + '")')
        for v in f.values:
            o.append('.value("' + v['name'] + '",' + c.namespace + '::' + c.name + '::' + f.name + '::' + v['name'] + ')') 
        o.append(';')

    inherit = ''
    if c.inherit:
        inherit = ',' + ','.join(c.inherit)
    
    if (c.classes == []):
        o.append('py::class_<' + c.namespace + '::' + c.name + inherit + '>(' + ctx_name + ' , "' + c.name + '"')     
        if c.comment:
            o.append(', "' + c.comment + '")')
        else:
            o.append(')')
    else:
        o.append('py::class_<' + c.namespace + '::' + c.name + '> ' + c.name.lower() + '(' + ctx_name + ', "' + c.name + '"')
        if c.comment:
            o.append(', "' + c.comment + '");')
        else:
            o.append(');')
        o.append(c.name.lower())

    for f in c.constructors:
        o.append('.def(py::init<')
        args = ','.join(f.argument_types)
        o.append(args + ' >')
        aa = []
        if f.arguments:
            o.append(',')
            for a in f.arguments:                
                aa.append('py::arg("' + a + '")')
            o.append(','.join(aa))
        o.append(')')
        
                
    for f in c.functions:
        if (f.name.endswith('==')):
            o.append('.def(py::self == py.self)')
        elif (f.name.endswith('!=')):
            o.append('.def(py::self != py.self)')
        else:
            o.append('.def("' + f.name + '", &' + c.namespace + '::' + c.name + '::' + f.name)
            if f.comment:
                o.append(',"' + f.comment + '"')
            o.append(')')
    for f in c.fields:
        o.append('.def_readwrite("' + f.name + '", &' + c.namespace + '::' + c.name + '::' + f.name)
        if f.comment:
            o.append(',"' + f.comment + '"')
        o.append(')')
    o.append(';')

    for cc in c.classes:
        print_class(cc, c.name.lower(), o)

def print_translation_unit(declarations, o):
    for d in declarations:
        if isinstance(d, Class):
            print_class(d, 'm', o)
        if isinstance(d, Enum):
            print_enum(d, 'm', o)
        if isinstance(d, Function):
            print_function(d, 'm', o)

def print_python_module(name, files, index, copts, o):
    o.append('#include "pybind11/pybind11.h"')
    o.append('namespace py = pybind11;')
    o.append('#include "pybind11/operators.h"')
    o.append('#include "pybind11/stl.h"')
    o.append('#include "pybind11/stl_bind.h"')
    o.append('PYBIND11_MODULE(' + name + ', m)')
    o.append('{')
    for f in args.files:
        o.append('// ' + f)
        translation_unit = index.parse(f, copts)
        declarations = build_declarations(translation_unit.cursor, f)
        print_translation_unit(declarations, o)
    o.append('}')



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate python bindings.')
    parser.add_argument('--name', type=str, required=True, help="name of the python module")
    parser.add_argument('--libclang', type=str, help="path to libclang.so on Linux / libclang.dylib on macOS")
    parser.add_argument('--copts', type=str, help="additional compiler options (pass with \" \" around them)")
    parser.add_argument('files', metavar='files', type=str, nargs='+', help="files to generate bindings for")
    args = parser.parse_args()


    libclang = ''
    if args.libclang:            
        libclang = args.libclang
    else:
        p = platform.system()
        if p == 'Darwin':
            libclang = '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/libclang.dylib'
        elif p == 'Linux':
            libclang = '/usr/lib/libclang.so'
        else:
            print('Could not find libclang in any of the default locations. You need to give the location of libclang by passing it with --libclang')
            sys.exit()
    clang.cindex.Config.set_library_file(libclang)           
    index = clang.cindex.Index.create()
    copts = ['-x', 'c++', '-std=c++11', '-D__CODE_GENERATOR__']
    if args.copts:
        copts.append(args.copts)
        
    o = []
    print_python_module(args.name, args.files, index, copts, o)
    s = '\n'.join(o)
    p = subprocess.Popen(["clang-format"], stdout=subprocess.PIPE, stdin = subprocess.PIPE)
    p.stdin.write(s)
    print(p.communicate()[0])
    p.stdin.close()
