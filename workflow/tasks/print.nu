#! /bin/env nu

ls | where type == dir | each { 
  print ([
    (ansi green)
    # '# ' 
    ($in.name | str uppercase)
    (ansi reset)
  ] | str join); 
  print ''; 
  ls $in.name | sort-by modified | where type == file | get name | each {
    let file = $in | path basename

    let yml = open $in
      | where element == yaml
      | first
      | get -o content

    if ($yml | is-not-empty) {
      let yml = $yml | from yml
      if ($yml.name | is-not-empty) {
        print $yml.name
        print ''
      }
    }
    
    print $file
    
  }; 
  print '' 
};

();
