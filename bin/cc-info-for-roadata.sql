-- Adding CC info to RPKI data

-- author: carlos@lacnic.net
-- date: 2017-07-15

-- Adding columns for country code information

ALTER TABLE roadata ADD COLUMN cc CHAR(2);
ALTER TABLE roadata ADD COLUMN origin_as_cc CHAR(2);

-- end

-- Adding prefix country code information

UPDATE roadata SET cc='ZZ' WHERE ta LIKE '%LACNIC%';

UPDATE roadata SET cc = 
    (select N.cc from numres as N 
    where roadata.istart>=N.istart 
        and roadata.istart<=N.iend 
        and (N.status='allocated' or N.status='assigned') 
        and type != 'asn') 
WHERE roadata.ta like '%LACNIC%';


-- Adding expected origin as country code information   

UPDATE roadata SET origin_as_cc='ZZ' WHERE ta LIKE '%LACNIC%';

UPDATE roadata SET origin_as_cc = 
    (select N.cc from numres as N 
        where roadata.origin_as2>=N.istart 
            and roadata.origin_as2<=N.iend 
            and (N.status='allocated' or N.status='assigned') 
            and N.type="asn" ) 
WHERE roadata.ta like '%LACNIC%';
