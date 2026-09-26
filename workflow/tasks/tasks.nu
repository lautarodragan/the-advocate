#! /bin/env nu

def main [] {
  
}

def "main ls" [
  --status (-s): string = "wip"
] {
  ls | where { $in.type == dir and ($status == "*" or $in.name == $status) } | each { 
    if $status == "*" {
      print ([
        (ansi green)
        # '# ' 
        ($in.name | str uppercase)
        (ansi reset)
      ] | str join); 
    }
    ls $in.name | sort-by name | where type == file | get name | each {
      let file = $in | path basename

      let yml = open $in
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
      
      print (['  ' (ansi green) $task_type (ansi reset) ': ' (ansi red_bold) $name (ansi reset)] | str join)
      # print (['  ' (ansi green) $task_type (ansi green)] | str join)
      # print (['    ' (ansi green) $file (ansi reset)] | str join)
      # print (['    ' (ansi reset) $file (ansi reset)] | str join)
      if ($yml | get -o description | is-not-empty) {
        print (['    ' (ansi reset) $yml.description (ansi reset)] | str join)
      }
      print '' 
      
    }; 
    print '' 
  };

  ();
}
