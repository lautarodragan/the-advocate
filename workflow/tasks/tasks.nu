#! /bin/env nu

def main [] {
  
}

def parse_file [file: string] {
  # let file = $in | path basename
    
  let yml = open $file
    | where element == yaml
    | first
    | get -o content

  let yml = if ($yml | is-not-empty) {
    $yml | from yml
  } else {
    null
  }

  let name = $yml | get -o name | default "(Not Named)"
  let task_type = $yml | get -o type | default "(no task type assigned)"
  let task_description = $yml | get -o description | default "(no task description)"
  
  return {
    file: $file,
    name: $name,
    task_type: $task_type,
    description: $task_description,
  }
}

def task_title [] {
  [(ansi green) $in.task_type (ansi reset) ': ' (ansi red_bold) $in.name (ansi reset)] | str join
}

def print_task [] {
  print ('  ' + ($in | task_title))
  # print (['    ' (ansi reset) $file (ansi reset)] | str join)
  print (['    ' (ansi reset) $in.description (ansi reset)] | str join)
  print '' 
}

def "main ls" [
  --status (-s): string = "doing"
] {
  ls | where { $in.type == dir and ($status == "*" or $in.name == $status) } | each { 
    if $status == "*" {
      print ([
        (ansi green)
        ($in.name | str uppercase)
        (ansi reset)
      ] | str join); 
    }

    let parsed = ls $in.name | where type == file | get name | each { parse_file $in } | sort-by task_type
    
    $parsed | each { print_task }
    
    print '' 
  };

  ();
}

# Elegir una tarea con filtro difuso y abrirla en $EDITOR.
def "main open" [
  --status (-s): string = "*"
] {
  let tasks = ls | where { $in.type == dir and ($status == "*" or $in.name == $status) } | each { |dir|
    ls $dir.name | where type == file | get name | each { parse_file $in | insert status $dir.name }
  } | flatten | sort-by { $in.status == done } status task_type

  let chosen = $tasks | input list --fuzzy --display { |t| [$t.status '  ' ($t | task_title) '  ' (ansi dark_gray) $t.description (ansi reset)] | str join } "Tarea:"
  if ($chosen | is-empty) { return }

  run-external ($env.EDITOR? | default micro) $chosen.file
}
