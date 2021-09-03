#!/usr/bin/python3

import argparse
import os
import re

from PropertyTree import PropertyNode

parser = argparse.ArgumentParser(description='autogen messages code.')
parser.add_argument('input', help='message definition file')
parser.add_argument('--namespace', help='optional namespace (for C++)')
parser.add_argument('--no-props', action='store_true', help="don't generate property system code.")
args = parser.parse_args()

if not os.path.isfile(args.input):
    print("Specified input file not found:", args.input)
    quit()

root = PropertyNode("/")
root.load(args.input)
#root.pretty_print()

if not root.hasChild("messages"):
    print("No message definition found in:", args.input)
    quit()

type_code = { "double": "d", "float": "f",
              "uint64_t": "Q", "int64_t": "q",
              "uint32_t": "L", "int32_t": "l",
              "uint16_t": "H", "int16_t": "h",
              "uint8_t": "B", "int8_t": "b",
              "bool": "B", "string": "H"
}

type_prop = { "double": "Double", "float": "Double",
              "uint64_t": "UInt64", "int64_t": "Int64",
              "uint32_t": "UInt", "int32_t": "Int",
              "uint16_t": "UInt", "int16_t": "Int",
              "uint8_t": "UInt", "int8_t": "Int",
              "bool": "Bool", "string": "String"
}

reserved_names = [ "id", "len", "payload", "_buf", "_i", "_pack_string",
                   "pack", "unpack" ]
reserved_names += list(type_code.keys())

basename, ext = os.path.splitext(args.input)

# namespace
namespace = "message"           # default
if args.namespace:
    namespace = args.namespace
elif root.hasChild("namespace"):
    namespace = root.getString("namespace")

# load and/or assign id numbers to message names
id_dict = root.getChild("id_dict")
next_id = 10
if id_dict.load(basename + ".ids"):
    # found an existing dictionary, determine next available id number
    for name in id_dict.getChildren(False):
        val = id_dict.getInt(name)
        if val >= next_id:
            next_id = val + 1
    print("loaded exisiting id dictionary, next available id:", next_id)

# scan messages and assign id's if needed
for i in range(root.getLen("messages")):
    m = root.getChild("messages/%d" % i)
    if not m.hasChild("name"):
        print("error: unnamed message ...")
        m.pretty_print()
        quit()
    name = m.getString("name")
    if m.hasChild("id"):
        val = m.getInt("id")
        id_dict.setInt(name, val)
        if val >= next_id:
            next_id = val + 1
    elif id_dict.hasChild(name):
        # already assigned an id
        pass
    else:
        # need to assign an id
        id_dict.setInt(name, next_id)
        next_id += 1
id_dict.pretty_print()

def field_name_helper(f):
    name = f.getString("name")
    # test for array form: ident[size]
    parts = re.split('([\w]+)\[(\w+)\]', name)
    # print("parts:", parts)
    if len(parts) == 4:
        name = parts[1]
        index = parts[2]
    else:
        index = None
    return (name, index)

def gen_cpp_header():
    result = []

    # test if any messages use "string"
    has_dynamic_string = False
    for i in range(root.getLen("messages")):
        m = root.getChild("messages/%d" % i)
        # quick checks
        for j in range(m.getLen("fields")):
            f = m.getChild("fields/%d" % j)
            name = f.getString("name")
            if f.getString("type") == "string":
                has_dynamic_string = True
                
    result.append("#pragma once")
    result.append("")
    result.append("// Ardupilot realloc() support")
    result.append("#if defined(ARDUPILOT_BUILD)")
    result.append("  #include <AP_HAL/AP_HAL.h>")
    result.append("  extern const AP_HAL::HAL& hal;");
    result.append("  #define REALLOC(X, Y) hal.util->std_realloc( (X), (Y) )")
    result.append("#else")
    result.append("  #define REALLOC(X, Y) std::realloc( (X), (Y) )")
    result.append("#endif")
    result.append("")
    result.append("#include <stdint.h>  // uint8_t, et. al.")
    result.append("#include <stdlib.h>  // malloc() / free()")
    result.append("#include <string.h>  // memcpy()")
    result.append("")
    if has_dynamic_string:
        result.append("#include <string>")
        result.append("using std::string;")
        result.append("")
    if not args.no_props:
        result.append("#include \"props2.h\"  // github.com/RiceCreekUAS/props/v2")
        result.append("")
    result.append("namespace %s {" % namespace)
    result.append("")
    result.append("static inline int32_t intround(float f) {")
    result.append("    return (int32_t)(f >= 0.0 ? (f + 0.5) : (f - 0.5));")
    result.append("}")
    result.append("")
    result.append("static inline uint32_t uintround(float f) {")
    result.append("    return (int32_t)(f + 0.5);")
    result.append("}")
    result.append("")

    # generate message id constants (and quick checks)
    result.append("// Message id constants")
    for i in range(root.getLen("messages")):
        m = root.getChild("messages/%d" % i)
        id = id_dict.getInt(m.getString("name"))
        result.append("const uint8_t %s_id = %d;" % (m.getString("name"), id))
        # quick checks
        for j in range(m.getLen("fields")):
            f = m.getChild("fields/%d" % j)
            name = f.getString("name")
            if name in reserved_names:
                print("Error: '%s' is reserved and cannot be used as a field name." % name)
                print("Aborting.")
                quit()
    result.append("")

    if root.getLen("constants"):
        result.append("// Constants")
        for i in range(root.getLen("constants")):
            m = root.getChild("constants/%d" % i)
            line = "static const %s %s = %s;" % (m.getString("type"), m.getString("name"), m.getString("value"))
            if m.hasChild("desc") != "":
                line += "  // %s" % m.getString("desc")
            result.append(line)
        result.append("")

    enum_dict = {}
    if root.getLen("enums"):
        result.append("// Enums")
        for i in range(root.getLen("enums")):
            m = root.getChild("enums/%d" % i)
            enum_dict[m.getString("name")] = 1
            result.append("enum class %s {" % m.getString("name"))
            for j in range(m.getLen("identifiers")):
                f = m.getChild("identifiers/%d" % j)
                line = "    %s = %d" % (f.getString("name"), j)
                if j < m.getLen("identifiers") - 1:
                    line += ","
                if f.hasChild("desc"):
                    line += "  // %s" % f.getString("desc")
                result.append(line)
            result.append("};")
        result.append("")
    
    for i in range(root.getLen("messages")):
        m = root.getChild("messages/%d" % i)
        print("Processing:", m.getString("name"))
        # quick checks
        for j in range(m.getLen("fields")):
            f = m.getChild("fields/%d" % j)
            name = f.getString("name")
            if name in reserved_names:
                print("Error: '%s' is reserved and cannot be used as a field name." % name)
                print("Aborting.")
                quit()

        # generate public c message class
        id = id_dict.getInt(m.getString("name"))
        result.append("// Message: %s (id: %d)" % (m.getString("name"), id))
        result.append("class %s_t {" % (m.getString("name")))
        result.append("public:")
        result.append("")
        for j in range(m.getLen("fields")):
            f = m.getChild("fields/%d" % j)
            line = "    %s %s" % (f.getString("type"), f.getString("name"))
            if f.hasChild("default"):
                line += " = %s" % f.getString("default")
            line += ";"
            result.append(line)
        result.append("")

        # generate private c packed struct
        result.append("    // internal structure for packing")
        result.append("    #pragma pack(push, 1)")
        result.append("    struct _compact_t {")
        count = m.getLen("fields")
        for j in range(count):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if f.hasChild("pack_type"):
                ptype = f.getString("pack_type")
            elif f.getString("type") == "string":
                ptype = "uint16_t"
            elif f.getString("type") in enum_dict:
                ptype = "uint8_t"
            else:
                ptype = f.getString("type")
            line = "        %s %s" % (ptype, name)
            if f.getString("type") == "string":
                line += "_len"
            if index:
                line += "[%s]" % index
            line += ";"
            result.append(line)
        result.append("    };")
        result.append("    #pragma pack(pop)")
        result.append("")

        # generate built in constants
        result.append("    // id, ptr to payload and len")
        id = id_dict.getInt(m.getString("name"))
        result.append("    static const uint8_t id = %s;" % id)
        result.append("    uint8_t *payload = nullptr;")
        result.append("    int len = 0;")
        result.append("")

        # need a destructor to free memory that pack() mallocs
        result.append("    ~%s_t() {" % (m.getString("name")))
        result.append("        free(payload);")
        result.append("    }")
        result.append("")
        
        # generate pack code
        result.append("    bool pack() {")
        result.append("        len = sizeof(_compact_t);")
        
        # add up dynamic packet size
        result.append("        // compute dynamic packet size (if neede)")
        result.append("        int size = len;")
        for j in range(count):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if index:
                if f.getString("type") == "string":
                    result.append("        for (int _i=0; _i<%s; _i++) size += %s[_i].length();" % (index, name))
            else:
                if f.getString("type") == "string":
                    result.append("        size += %s.length();" % name)
        result.append("        payload = (uint8_t *)REALLOC(payload, size);")

        if count > 0:
            # copy values
            result.append("        // copy values")
            result.append("        _compact_t *_buf = (_compact_t *)payload;")
        for j in range(count):
            line = "        ";
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if index:
                line += "for (int _i=0; _i<%s; _i++) " % index
            line += "_buf->%s" % name
            if f.getString("type") == "string":
                line += "_len"
            if index:
                line += "[_i]"
            line += " = "
            #line += "_buf.%s = " % f.getString("name")
            if f.hasChild("pack_type"):
                ptype = f.getString("pack_type")
                if ptype[0] == "i":
                    line += "intround("
                else:
                    line += "uintround("
                line += "%s" % name
                if index:
                    line += "[_i]"
                if f.hasChild("pack_scale"):
                    line += " * %s" % f.getDouble("pack_scale")
                line += ")"
            else:
                if f.getString("type") in enum_dict:
                    line += "(uint8_t)"
                line += "%s" % name
                if index:
                    line += "[_i]"
                if f.getString("type") == "string":
                    line += ".length()"
            line += ";"
            result.append(line)
        # append string data if needed
        for j in range(count):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if index:
                if f.getString("type") == "string":
                    result.append("        for (int _i=0; _i<%s; _i++) {" % index)
                    result.append("            memcpy(&(payload[len]), %s[_i].c_str(), %s[_i].length());" % (name, name))
                    result.append("            len += %s[_i].length();" % name)
                    result.append("        }")
            else:
                if f.getString("type") == "string":
                    result.append("        memcpy(&(payload[len]), %s.c_str(), %s.length());" % (name, name))
                    result.append("        len += %s.length();" % name)
        result.append("        return true;")
        result.append("    }")
        result.append("")

        # generate unpack code
        result.append("    bool unpack(uint8_t *external_message, int message_size) {")
        if count > 0:
            result.append("        _compact_t *_buf = (_compact_t *)external_message;");
        result.append("        len = sizeof(_compact_t);")
        for j in range(count):
            line = "        ";
            f = m.getChild("fields/%d" % j)
            if f.getString("type") != "string":
                (name, index) = field_name_helper(f)
                if index:
                    line += "for (int _i=0; _i<%s; _i++) " % index
                line += name
                if index:
                    line += "[_i]"
                line += " = "
                if f.hasChild("pack_scale"):
                    line += "_buf->%s" % name
                    if index:
                        line += "[_i]"
                    line += " / (float)%s" % f.getDouble("pack_scale")
                    ptype = f.getString("pack_type")
                else:
                    if f.getString("type") in enum_dict:
                        line += "(%s)" % f.getString("type")                    
                    line += "_buf->%s" % name
                    if index:
                        line += "[_i]"
                line += ";"
                result.append(line)
        # unpack string data if needed
        for j in range(count):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if index:
                if f.getString("type") == "string":
                    result.append("        for (int _i=0; _i<%s; _i++) {" % index)
                    result.append("            %s[_i] = string((char *)&(external_message[len]), _buf->%s_len[_i]);" % (name, name))
                    result.append("            len += _buf->%s_len[_i];" % name)
                    result.append("        }")
            else:
                if f.getString("type") == "string":
                    result.append("        %s = string((char *)&(external_message[len]), _buf->%s_len);" % (name, name))
                    result.append("        len += _buf->%s_len;" % name)
        result.append("        return true;")
        result.append("    }")

        if not args.no_props:
            # generate msg2props code
            count = m.getLen("fields")
            result.append("")
            result.append("    void msg2props(string _path, int _index = -1) {")
            result.append("        if ( _index >= 0 ) {");
            result.append("            _path += \"/\" + std::to_string(_index);")
            result.append("        }");
            result.append("        PropertyNode node(_path.c_str());");
            result.append("        msg2props(node);");
            result.append("    }");
            result.append("")
            result.append("    void msg2props(PropertyNode node) {")
            if count > 0:
                for j in range(count):
                    line = "        ";
                    f = m.getChild("fields/%d" % j)
                    (name, index) = field_name_helper(f)
                    if index:
                        line += "for (int _i=0; _i<%s; _i++) " % index
                    if f.getString("type") in type_prop:
                        tp = type_prop[f.getString("type")]
                    else:
                        tp = "Int"
                    line += "node.set%s(\"%s\"" % (tp, name)
                    line += ", "
                    if f.getString("type") in enum_dict:
                        line += "(%s)" % f.getString("type")                    
                    line += "%s" % name
                    if index:
                        line += "[_i], _i"
                    line += ");"
                    result.append(line)
            result.append("    }")

            # generate props2msg code
            count = m.getLen("fields")
            result.append("")
            result.append("    void props2msg(string _path, int _index = -1) {")
            result.append("        if ( _index >= 0 ) {");
            result.append("            _path += \"/\" + std::to_string(_index);")
            result.append("        }");
            result.append("        PropertyNode node(_path.c_str());");
            result.append("        props2msg(node);");
            result.append("    }");
            result.append("")
            result.append("    void props2msg(PropertyNode node) {")
            if count > 0:
                for j in range(count):
                    line = "        ";
                    f = m.getChild("fields/%d" % j)
                    (name, index) = field_name_helper(f)
                    if index:
                        line += "for (int _i=0; _i<%s; _i++) " % index
                    if f.getString("type") in type_prop:
                        tp = type_prop[f.getString("type")]
                    else:
                        tp = "Int"
                    line += name
                    if index:
                        line += "[_i]"
                    line += " = node.get%s(\"%s\"" % (tp, name)
                    if index:
                        line += ", _i"
                    line += ")"
                    if f.getString("type") in enum_dict:
                        line += "(%s)" % f.getString("type")                    
                    line += ";"
                    result.append(line)
            result.append("    }")
        
        result.append("};")
        result.append("")
    result.append("} // namespace %s" % namespace)
    return result

def gen_python_module():
    result = []

    result.append("import struct")
    if not args.no_props:
        result.append("from PropertyTree import PropertyNode")
    result.append("")

    # generate message id constants
    result.append("# Message id constants")
    for i in range(root.getLen("messages")):
        m = root.getChild("messages/%d" % i)
        id = id_dict.getInt(m.getString("name"))
        result.append("%s_id = %s" % (m.getString("name"), id))
    result.append("")

    constants_dict = {}
    if root.getLen("constants"):
        result.append("# Constants")
        for i in range(root.getLen("constants")):
            m = root.getChild("constants/%d" % i)
            constants_dict[m.getString("name")] = m.getInt("value")
            line = "%s = %s" % (m.getString("name"), m.getString("value"))
            if m.hasChild("desc") != "":
                line += "  # %s" % m.getString("desc")
            result.append(line)
        result.append("")
    
    enum_dict = {}
    if root.getLen("enums"):
        result.append("# Enums")
        for i in range(root.getLen("enums")):
            m = root.getChild("enums/%d" % i)
            enum_dict[m.getString("name")] = 1
            for j in range(m.getLen("identifiers")):
                f = m.getChild("identifiers/%d" % j)
                line = "%s_%s = %d" % (m.getString("name"), f.getString("name"), j)
                if f.hasChild("desc"):
                    line += "  # %s" % f.getChild("desc")
                result.append(line)
        result.append("")
    
    for i in range(root.getLen("messages")):
        m = root.getChild("messages/%d" % i)
        print("Processing:", m.getString("name"))
        # generate python pack string and sanity check
        pack_string = "<"       # little endian byte order
        has_dynamic_string = False
        for j in range(m.getLen("fields")):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if f.hasChild("pack_type"):
                pack_code = type_code[f.getString("pack_type")]
            elif f.getString("type") in enum_dict:
                pack_code = "B"
            else:
                pack_code = type_code[f.getString("type")]
            if index:
                if index in constants_dict:
                    pack_string += pack_code * constants_dict[index]
                else:
                    pack_string += pack_code * int(index)
            else:
                pack_string += pack_code
            if name in reserved_names:
                print("Error: '%s' is reserved and cannot be used as a field name." % name)
                print("Aborting.")
                quit()

        # generate public message class
        id = id_dict.getInt(m.getString("name"))
        result.append("# Message: %s" % m.getString("name"))
        result.append("# Id: %d" % id)
        result.append("class %s():" % (m.getString("name")))
        result.append("    id = %s" % id)
        result.append("    _pack_string = \"%s\"" % pack_string)
        result.append("    _struct = struct.Struct(_pack_string)")
        result.append("")
        result.append("    def __init__(self, msg=None):")
        result.append("        # public fields")
        for j in range(m.getLen("fields")):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            t = f.getString("type")
            line = "        self.%s = " % name
            if index:
                line += "["
            if f.hasChild("default"):
                line += f.getString("default")
            elif t == "double" or t == "float":
                line += "0.0"
            elif "int" in t:
                line += "0"
            elif t in enum_dict:
                line += "0"
            elif t == "bool":
                line += "False"
            elif t == "string":
                line += "\"\""
                has_dynamic_string = True
            else:
                line += "None"
            if index:
                line += "] * %s" % index
            result.append(line)
        result.append("        # unpack if requested")
        result.append("        if msg: self.unpack(msg)")
        result.append("")

        # generate pack code
        result.append("    def pack(self):")
        result.append("        msg = self._struct.pack(")
        count = m.getLen("fields")
        for j in range(count):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if index:
                if index in constants_dict:
                    index = int(constants_dict[index])
                else:
                    index = int(index)
                for k in range(index):
                    line = "                  "
                    if f.hasChild("pack_scale"):
                        line += "int(round(self.%s[%d] * %s))" % (name, k, f.getDouble("pack_scale"))
                    elif f.getString("type") == "string":
                        line += "len(self.%s[%d])" % (name, k)
                    else:
                        line += "self.%s[%d]" % (name, k)
                    if j < count - 1 or k < index - 1:
                        line += ","
                    else:
                        line += ")"
                    result.append(line)
            else:
                line = "                  "
                if f.hasChild("pack_scale"):
                    line += "int(round(self.%s * %s))" % (name, f.getDouble("pack_scale"))
                elif f.getString("type") == "string":
                    line += "len(self.%s)" % (name)
                else:
                    line += "self.%s" % f.getString("name")
                if j < count - 1:
                    line += ","
                else:
                    line += ")"
                result.append(line)
        # append string data if needed
        for j in range(count):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if index:
                if index in constants_dict:
                    index = int(constants_dict[index])
                else:
                    index = int(index)
                for k in range(index):
                    if f.getString("type") == "string":
                        result.append("        msg += str.encode(self.%s[%d])" % (name, k))
            else:
                if f.getString("type") == "string":
                    result.append("        msg += str.encode(self.%s)" % name)
                        
        result.append("        return msg")
        result.append("")

        # generate unpack code
        result.append("    def unpack(self, msg):")
        if has_dynamic_string:
            result.append("        base_len = struct.calcsize(self._pack_string)")
            result.append("        extra = msg[base_len:]")
            result.append("        msg = msg[:base_len]")
            for j in range(count):
                f = m.getChild("fields/%d" % j)
                (name, index) = field_name_helper(f)
                if index:
                    result.append("        self.%s_len = [0] * %s" % (name, index))
        for j in range(count):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if index:
                if index in constants_dict:
                    index = int(constants_dict[index])
                else:
                    index = int(index)
                for k in range(index):
                    if j == 0 and k == 0:
                        line = "        ("
                    else:
                        line = "         "
                    line += "self.%s" % name
                    if f.getString("type") == "string":
                        line += "_len"
                    line += "[%d]" % k
                    if j < count - 1 or k < index - 1:
                        line += ","
                    else:
                        if count == 1:
                            line += ","
                        line += ") = self._struct.unpack(msg)"
                    result.append(line)
            else:
                if j == 0:
                    line = "        ("
                else:
                    line = "         "
                line += "self.%s" % name
                if f.getString("type") == "string":
                    line += "_len"
                if j < count - 1:
                    line += ","
                else:
                    if count == 1:
                        line += ","
                    line += ") = self._struct.unpack(msg)"
                result.append(line)
        for j in range(count):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if index:
                if index in constants_dict:
                    index = int(constants_dict[index])
                else:
                    index = int(index)
                for k in range(index):
                    if f.hasChild("pack_scale"):
                        line = "        self.%s[%d] /= %s" % (name, k, f.getDouble("pack_scale"))
                        result.append(line)
            else:
                if f.hasChild("pack_scale"):
                    line = "        self.%s /= %s" % (name, f.getDouble("pack_scale"))
                    result.append(line)
        # unpack string data if needed
        for j in range(count):
            f = m.getChild("fields/%d" % j)
            (name, index) = field_name_helper(f)
            if index:
                if index in constants_dict:
                    index = int(constants_dict[index])
                else:
                    index = int(index)
                for k in range(index):
                    if f.getString("type") == "string":
                        result.append("        self.%s[%d] = extra[:self.%s_len[%d]].decode()" % (name, k, name, k))
                        result.append("        extra = extra[self.%s_len[%d]:]" % (name, k))
            else:
                if f.getString("type") == "string":
                    result.append("        self.%s = extra[:self.%s_len].decode()" % (name, name))
                    result.append("        extra = extra[self.%s_len:]" % name)
        
        if not args.no_props:
            # generate msg2props code
            count = m.getLen("fields")
            result.append("")
            result.append("    def msg2props(self, node):")
            if count > 0:
                for j in range(count):
                    line = "        ";
                    f = m.getChild("fields/%d" % j)
                    (name, index) = field_name_helper(f)
                    if index:
                        line += "for _i in range(%s): " % index
                    if f.getString("type") in type_prop:
                        tp = type_prop[f.getString("type")]
                    else:
                        tp = "Int"
                    line += "node.set%s(\"%s\"" % (tp, name)
                    line += ", "
                    if f.getString("type") in enum_dict:
                        line += "(%s)" % f.getString("type")                    
                    line += "self.%s" % name
                    if index:
                        line += "[_i]"
                    if index:
                        line += ", _i"
                    line += ")"
                    result.append(line)

            # generate props2msg code
            count = m.getLen("fields")
            result.append("")
            result.append("    def props2msg(self, node):")
            if count > 0:
                for j in range(count):
                    line = "        ";
                    f = m.getChild("fields/%d" % j)
                    (name, index) = field_name_helper(f)
                    if index:
                        line += "for _i in range(%s): " % index
                    if f.getString("type") in type_prop:
                        tp = type_prop[f.getString("type")]
                    else:
                        tp = "Int"
                    line += name
                    if index:
                        line += "[_i]"
                    line += " = node.get%s(\"%s\"" % (tp, name)
                    if index:
                        line += ", _i"
                    line += ")"
                    if f.getString("type") in enum_dict:
                        line += "(%s)" % f.getString("type")                    
                    result.append(line)
            result.append("")

    return result

if True:
    print("Generating C++ header:")
    code = gen_cpp_header()
    f = open(basename + ".h", "w")
    for line in code:
        f.write(line + "\n")
    f.close()

if True:
    print("Generating Python3 code:")
    code = gen_python_module()
    f = open(basename + ".py", "w")
    for line in code:
        f.write(line + "\n")
    f.close()

id_dict.pretty_print()
id_dict.save(basename + ".ids")
