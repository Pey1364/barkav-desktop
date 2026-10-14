Option Explicit
On Error Resume Next

Dim shell, fso, folder, command, arguments, i
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Environment("PROCESS")("PYTHONUTF8") = "1"
shell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"

arguments = ""
For i = 0 To WScript.Arguments.Count - 1
    arguments = arguments & " """ & Replace(WScript.Arguments(i), """", """""") & """"
Next

command = "pyw -3 """ & folder & "\launcher_stage18_7.py""" & arguments
Err.Clear
shell.Run command, 0, False
If Err.Number <> 0 Then
    Err.Clear
    command = "pythonw """ & folder & "\launcher_stage18_7.py""" & arguments
    shell.Run command, 0, False
End If
