#! /bin/env nu

ls | where type == dir | each { 
  print ([
    (ansi green)
    # '# ' 
    ($in.name | str uppercase)
    (ansi reset)
  ] | str join); 
  # print ''; 
  ls $in.name | sort-by modified | where type == file | get name | each {
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
    
    # print $name
    print (['  ' (ansi red) $name (ansi reset)] | str join)
    print (['    ' (ansi green) $file (ansi reset)] | str join)
    if ($yml | get -o description | is-not-empty) {
      print (['    ' (ansi green) $yml.description (ansi reset)] | str join)
    }
    
  }; 
  print '' 
};

();
