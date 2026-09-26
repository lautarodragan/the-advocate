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

def "main ls" [
  --status (-s): string = "wip"
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
    
    $parsed | each {
      print (['  ' (ansi green) $in.task_type (ansi reset) ': ' (ansi red_bold) $in.name (ansi reset)] | str join)
      # print (['    ' (ansi reset) $file (ansi reset)] | str join)
      print (['    ' (ansi reset) $in.description (ansi reset)] | str join)
      print '' 
      
    }; 
    print '' 
  };

  ();
}
